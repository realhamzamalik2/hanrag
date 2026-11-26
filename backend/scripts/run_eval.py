"""HanRAG evaluation: retrieval ablation + end-to-end answer quality.

Retrieval ablation (no LLM calls): every configuration retrieves the top 10 passages for
each question; a passage counts as relevant if it contains the question's evidence phrase.
  bm25 (whitespace) | bm25 (Kiwi) | vector | hybrid (whitespace) | hybrid (Kiwi) | hybrid + reranker

End-to-end (Gemini free tier): the default pipeline answers all 50 questions. Measured:
answer correctness (required facts present), citation grounding (a cited passage contains
the evidence), faithfulness (LLM judge: every claim supported by the cited passages),
correct refusals on unanswerable questions, false refusals, and latency per stage.

Usage (from backend/, with the API stopped so models are not loaded twice):
  uv run python -m scripts.run_eval                 # everything
  uv run python -m scripts.run_eval --retrieval     # ablation only (no API calls)
  uv run python -m scripts.run_eval --generation    # end-to-end only
Outputs: eval/results/summary.json, retrieval_runs.json, generation_runs.json, RESULTS.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from app.config import ROOT_DIR, get_settings
from app.db.session import init_db, session_scope
from app.evaluation import (
    KS,
    EvalQuestion,
    answer_matches,
    first_relevant_rank,
    is_relevant,
    latency_stats,
    load_questions,
    retrieval_metrics,
    threshold_sweep,
)
from app.generation.prompts import PROMPT_VERSION
from app.logging_setup import setup_logging

EVAL_DIR = ROOT_DIR / "eval"
RESULTS = EVAL_DIR / "results"
CACHE = EVAL_DIR / "runs"

ARMS = [
    ("bm25_ws", "BM25, whitespace tokens", "bm25", "whitespace"),
    ("bm25_kiwi", "BM25, Kiwi morphemes", "bm25", "kiwi"),
    ("vector", "Vector (bge-m3 int8)", "vector", "kiwi"),
    ("hybrid_ws", "Hybrid RRF, whitespace", "hybrid", "whitespace"),
    ("hybrid_kiwi", "Hybrid RRF, Kiwi", "hybrid", "kiwi"),
    ("hybrid_rerank", "Hybrid RRF + reranker", "hybrid_rerank", "kiwi"),
]
GROUPS = {"ko": ("ko",), "en": ("en",), "cross": ("cross_en_ko", "cross_ko_en")}
THRESHOLDS = [0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]

JUDGE_VERSION = 2

JUDGE_SYSTEM = """You check whether an answer is supported by source passages.
Return JSON only: {"supported": true|false, "unsupported": ["claim", ...]}
supported = true only if EVERY factual claim in the answer is stated in or directly implied
by the passages. Language differences do not matter. Each passage is labelled with the
number the answer uses to cite it."""


def log(msg: str) -> None:
    print(msg, flush=True)


def by_group(qs: list[EvalQuestion], ranks: dict[str, int | None]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for g, types in GROUPS.items():
        rs = [ranks[q.id] for q in qs if q.type in types]
        if rs:
            out[g] = {**retrieval_metrics(rs), "n": len(rs)}
    return out


# ---------------------------------------------------------------- retrieval ablation
def run_retrieval(qs: list[EvalQuestion]) -> dict[str, Any]:
    from app.retrieval.hybrid import retrieve

    answerable = [q for q in qs if q.answerable]
    per_q: dict[str, dict[str, Any]] = defaultdict(dict)
    arms_out = []
    for arm_id, label, mode, tok in ARMS:
        t_arm = time.perf_counter()
        ranks: dict[str, int | None] = {}
        lat: list[float] = []
        top_scores: dict[str, float] = {}
        targets = qs if mode == "hybrid_rerank" else answerable  # gate analysis needs all
        for i, q in enumerate(targets, start=1):
            with session_scope() as s:
                t0 = time.perf_counter()
                res = retrieve(s, q.question, mode=mode, tokenizer=tok,  # type: ignore[arg-type]
                               k_final=10)
                lat.append((time.perf_counter() - t0) * 1000)
            texts = [c.text for c in res.final]
            top_scores[q.id] = res.top_score
            if q.answerable:
                ranks[q.id] = first_relevant_rank(texts, q.evidence)
                per_q[q.id][arm_id] = ranks[q.id]
            if i % 10 == 0:
                log(f"  {arm_id}: {i}/{len(targets)}")
        metrics = retrieval_metrics(ranks.values())
        arms_out.append({
            "id": arm_id, "label": label, "mode": mode, "tokenizer": tok, "translate": False,
            "overall": metrics, "by_type": by_group(answerable, ranks),
            "latency_ms": latency_stats(lat),
        })
        log(f"[{arm_id}] recall@5={metrics['recall@5']:.2f} mrr={metrics['mrr@10']:.3f} "
            f"({time.perf_counter() - t_arm:.0f}s)")
        if mode == "hybrid_rerank":
            gate = {
                "answerable_scores": [top_scores[q.id] for q in answerable],
                "unanswerable_scores": [top_scores[q.id] for q in qs if not q.answerable],
            }
    sweep = threshold_sweep(gate["answerable_scores"], gate["unanswerable_scores"], THRESHOLDS)
    (RESULTS / "retrieval_runs.json").write_text(
        json.dumps({"ranks": per_q, "gate_scores": gate}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return {"arms": arms_out,
            "refusal_gate": {"current": get_settings().min_rerank_score, "sweep": sweep}}


# ---------------------------------------------------------------- end to end
def _with_retries(fn, *args, tries: int = 4, **kwargs):  # type: ignore[no-untyped-def]
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            transient = any(c in msg for c in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED",
                                                "timed out", "Timeout"))
            if not transient or attempt == tries - 1:
                raise
            wait = 15 * (attempt + 1)
            log(f"    transient error ({msg[:60]}...), retrying in {wait}s")
            time.sleep(wait)
    return None


def cited_numbers(answer: str, n: int) -> list[int]:
    """Citation numbers in order of first appearance, matching extract_citations()."""
    seen: list[int] = []
    for m in re.finditer(r"\[(\d+)\]", answer):
        k = int(m.group(1))
        if k not in seen:
            seen.append(k)
    return seen[:n]


def judge(answer: str, passages: list[str], numbers: list[int] | None = None) -> dict[str, Any]:
    """LLM judge. Passages keep the numbers the answer cites them by: renumbering them 1..n
    made "[3]" point at nothing, and correct answers were marked unsupported."""
    from app.generation import llm

    nums = numbers if numbers and len(numbers) == len(passages) else list(
        range(1, len(passages) + 1))
    prompt = ("Passages:\n\n" + "\n\n".join(f"[{k}] {p}" for k, p in zip(nums, passages,
                                                                         strict=True))
              + f"\n\nAnswer:\n{answer}")
    text, _ = _with_retries(llm.generate_json, JUDGE_SYSTEM, prompt)
    data = json.loads(text)
    return {"supported": bool(data.get("supported")),
            "unsupported": data.get("unsupported") or []}


def _rejudge(cache: dict[str, Any], cache_file: Any, pause: float) -> None:
    """Re-judge answers judged by an older judge version (no new answers are generated)."""
    stale = [r for r in cache.values()
             if r.get("cited") and "judge" in r and r.get("judge_version") != JUDGE_VERSION]
    if stale:
        log(f"Re-judging {len(stale)} answers in {cache_file.name} with judge v{JUDGE_VERSION}")
    for r in stale:
        nums = r.get("cited_numbers") or cited_numbers(r["answer"], len(r["cited"]))
        r["cited_numbers"] = nums
        r["judge"] = _with_retries(judge, r["answer"], r["cited"], nums)
        r["judge_version"] = JUDGE_VERSION
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  re-judged {r['id']}: supported={r['judge']['supported']}")
        time.sleep(pause)


def _rejudge_baseline(baseline: dict[str, Any], pause: float) -> None:
    f = CACHE / f"generation_{_config_key(baseline['config'])}.json"
    if not f.exists():
        return
    cache = json.loads(f.read_text(encoding="utf-8"))
    _rejudge(cache, f, pause)
    judged = [r for r in cache.values()
              if r["type"] != "unanswerable" and not r["refused"] and "judge" in r]
    if judged:
        baseline["faithful"] = round(sum(r["judge"]["supported"] for r in judged) / len(judged), 4)


def run_generation(qs: list[EvalQuestion], use_judge: bool, pause: float) -> dict[str, Any]:
    from app.generation import llm
    from app.rag import answer_question

    if not llm.is_configured():
        raise SystemExit("GEMINI_API_KEY / GEMINI_MODEL missing in .env")
    s = get_settings()
    config = {"mode": s.retrieval_mode, "tokenizer": s.bm25_tokenizer, "k": s.top_k_final,
              "rewrite": s.query_rewrite, "model": s.gemini_model,
              "min_rerank_score": s.min_rerank_score, "embed": s.embed_model,
              "rerank_match_lang": s.rerank_match_lang, "prompt": PROMPT_VERSION}
    cache_file = CACHE / f"generation_{_config_key(config)}.json"
    cache: dict[str, Any] = (json.loads(cache_file.read_text(encoding="utf-8"))
                             if cache_file.exists() else {})

    for i, q in enumerate(qs, start=1):
        if q.id in cache:
            continue
        a = _with_retries(answer_question, q.question, None)
        reranked = a.retrieval.reranked if a.retrieval else []
        row = {
            "id": q.id, "type": q.type, "question": q.question, "answer": a.answer,
            "refused": a.refused, "refusal_reason": a.refusal_reason,
            "standalone": a.standalone_query,
            "translation": a.retrieval.extra_queries if a.retrieval else [],
            "cited": [c.chunk.text for c in a.citations],
            "cited_numbers": [c.number for c in a.citations],
            "rank_translated": (first_relevant_rank([c.text for c in reranked], q.evidence)
                                if q.answerable else None),
            "stages_ms": a.stages_ms, "total_ms": a.total_ms,
        }
        if q.answerable and not a.refused:
            row["correct"] = answer_matches(a.answer, q.must)
            row["grounded"] = any(is_relevant(t, q.evidence) for t in row["cited"])
            if use_judge and row["cited"]:
                time.sleep(pause)
                row["judge"] = judge(a.answer, row["cited"], row["cited_numbers"])
                row["judge_version"] = JUDGE_VERSION
        cache[q.id] = row
        cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"  [{i}/{len(qs)}] {q.id} refused={a.refused} "
            f"correct={row.get('correct')} {a.total_ms / 1000:.1f}s")
        time.sleep(pause)

    if use_judge:
        _rejudge(cache, cache_file, pause)

    rows = [cache[q.id] for q in qs]
    ans = [r for r in rows if r["type"] != "unanswerable"]
    una = [r for r in rows if r["type"] == "unanswerable"]
    answered = [r for r in ans if not r["refused"]]
    judged = [r for r in answered if "judge" in r]

    def rate(xs: list[Any]) -> float:
        return round(sum(1 for x in xs if x) / len(xs), 4) if xs else 0.0

    stages: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        for k, v in r["stages_ms"].items():
            stages[k].append(v)
    by_type: dict[str, Any] = {}
    for g, types in {**GROUPS, "unanswerable": ("unanswerable",)}.items():
        rs = [r for r in rows if r["type"] in types]
        if not rs:
            continue
        if g == "unanswerable":
            by_type[g] = {"n": len(rs), "refused": rate([r["refused"] for r in rs])}
        else:
            by_type[g] = {"n": len(rs), "correct": rate([r.get("correct") for r in rs]),
                          "refused": rate([r["refused"] for r in rs])}
    ranks_t = [r["rank_translated"] for r in ans]
    (RESULTS / "generation_runs.json").write_text(
        json.dumps({"config": config, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return {
        "config": config, "n": len(rows),
        "answer_correct": rate([r.get("correct") for r in ans]),
        "answer_correct_when_answered": rate([r.get("correct") for r in answered]),
        "citation_grounded": rate([r.get("grounded") for r in answered]),
        "faithful": rate([r["judge"]["supported"] for r in judged]) if judged else None,
        "judged": len(judged),
        "same_language": rate([_same_language(r) for r in answered]),
        "unanswerable_refused": rate([r["refused"] for r in una]),
        "answerable_refused": rate([r["refused"] for r in ans]),
        "by_type": by_type,
        "latency_ms": {k: round(statistics.fmean(v), 1) for k, v in stages.items()},
        "total_ms": latency_stats([r["total_ms"] for r in rows]),
        "retrieval_with_translation": {**retrieval_metrics(ranks_t),
                                       "by_type": by_group([q for q in qs if q.answerable],
                                                           {q.id: cache[q.id]["rank_translated"]
                                                            for q in qs if q.answerable})},
    }


def _same_language(row: dict[str, Any]) -> bool:
    """The answer is written in the question's language (citations and names aside)."""
    from app.ingestion.korean import detect_lang

    q = detect_lang(row["question"])
    a = detect_lang(row["answer"])
    return q == "mixed" or a == "mixed" or q == a


def _config_key(config: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(config, sort_keys=True).encode()).hexdigest()[:10]


def _baseline_same_language(config: dict[str, Any]) -> float | None:
    """Recompute the language metric for a baseline saved before the metric existed."""
    f = CACHE / f"generation_{_config_key(config)}.json"
    if not f.exists():
        return None
    rows = [r for r in json.loads(f.read_text(encoding="utf-8")).values()
            if r["type"] != "unanswerable" and not r["refused"]]
    return round(sum(_same_language(r) for r in rows) / len(rows), 4) if rows else None


BASELINE_KEYS = ("answer_correct", "faithful", "citation_grounded", "same_language",
                 "unanswerable_refused", "answerable_refused")


# ---------------------------------------------------------------- report
def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def write_markdown(summary: dict[str, Any]) -> None:
    lines = ["# HanRAG evaluation results", "",
             f"Generated {summary['generated_at']} on {summary['dataset']['n']} questions "
             f"({summary['dataset']['by_type']}).", ""]
    r = summary.get("retrieval")
    if r:
        lines += ["## Retrieval ablation (top 10 passages, no query translation)", "",
                  "| Configuration | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | "
                  "Korean R@5 | English R@5 | Cross-lingual R@5 | Median latency |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for a in r["arms"]:
            o, bt = a["overall"], a["by_type"]
            lines.append(
                f"| {a['label']} | {pct(o['recall@1'])} | {pct(o['recall@3'])} | "
                f"{pct(o['recall@5'])} | {pct(o['recall@10'])} | {o['mrr@10']:.3f} | "
                f"{pct(bt.get('ko', {}).get('recall@5'))} | {pct(bt.get('en', {}).get('recall@5'))} | "
                f"{pct(bt.get('cross', {}).get('recall@5'))} | {a['latency_ms']['p50'] / 1000:.1f} s |")
        lines += ["", "### Early refusal gate (top reranker score below threshold)", "",
                  "| Threshold | Unanswerable refused | Answerable wrongly refused |",
                  "|---|---|---|"]
        for row in r["refusal_gate"]["sweep"]:
            lines.append(f"| {row['threshold']} | {pct(row['unanswerable_refused'])} | "
                         f"{pct(row['answerable_refused'])} |")
        lines.append("")
    g = summary.get("generation")
    if g:
        rt = g["retrieval_with_translation"]
        lines += ["## End-to-end answers (default pipeline)", "",
                  f"Config: {g['config']}", "",
                  "| Metric | Value |", "|---|---|",
                  f"| Answer correct (all answerable) | {pct(g['answer_correct'])} |",
                  f"| Answer correct (when it answered) | {pct(g['answer_correct_when_answered'])} |",
                  f"| Citation grounded (a cited passage has the evidence) | {pct(g['citation_grounded'])} |",
                  f"| Faithful (LLM judge, {g['judged']} answers) | {pct(g['faithful'])} |",
                  f"| Unanswerable correctly refused | {pct(g['unanswerable_refused'])} |",
                  f"| Answerable wrongly refused | {pct(g['answerable_refused'])} |",
                  f"| Retrieval R@5 with query translation | {pct(rt['recall@5'])} "
                  f"(cross-lingual {pct(rt['by_type'].get('cross', {}).get('recall@5'))}) |",
                  f"| Answer in the question's language | {pct(g.get('same_language'))} |",
                  f"| Median total time | {g['total_ms']['p50'] / 1000:.1f} s |", "",
                  "Mean time per stage: " + ", ".join(
                      f"{k} {v / 1000:.1f} s" for k, v in g["latency_ms"].items()), ""]
    b = summary.get("generation_baseline")
    if g and b:
        labels = {"answer_correct": "Answer correct", "faithful": "Faithful (judge)",
                  "citation_grounded": "Citation grounded",
                  "same_language": "Answer in the question's language",
                  "unanswerable_refused": "Unanswerable refused",
                  "answerable_refused": "Answerable wrongly refused"}
        lines += ["## Before and after the error-analysis fixes", "",
                  f"Baseline config: {b['config']}", "",
                  "| Metric | Baseline | Now |", "|---|---|---|"]
        lines += [f"| {labels[k]} | {pct(b.get(k))} | {pct(g.get(k))} |" for k in BASELINE_KEYS]
        lines.append("")
    (RESULTS / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval", action="store_true")
    ap.add_argument("--generation", action="store_true")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--pause", type=float, default=2.0, help="seconds between Gemini calls")
    args = ap.parse_args()
    do_r = args.retrieval or not args.generation
    do_g = args.generation or not args.retrieval

    setup_logging("WARNING")
    init_db()
    RESULTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    qs = load_questions(EVAL_DIR / "dataset" / "qa.jsonl")
    summary_path = RESULTS / "summary.json"
    summary: dict[str, Any] = (json.loads(summary_path.read_text(encoding="utf-8"))
                               if summary_path.exists() else {})
    types: dict[str, int] = defaultdict(int)
    for q in qs:
        types[q.type] += 1
    s = get_settings()
    summary.update({
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "dataset": {"n": len(qs), "by_type": dict(types)},
        "models": {"embedder": s.embed_model, "reranker": s.rerank_model, "llm": s.gemini_model},
        "ks": list(KS),
    })
    if do_r:
        log(f"Retrieval ablation: {len(ARMS)} configurations x {len(qs)} questions")
        summary["retrieval"] = run_retrieval(qs)
    if do_g:
        log(f"End-to-end: {len(qs)} questions with the default pipeline")
        previous = summary.get("generation")
        summary["generation"] = run_generation(qs, not args.no_judge, args.pause)
        # Keep the first run with a different config as the baseline for a before/after table.
        if (previous and "generation_baseline" not in summary
                and previous["config"] != summary["generation"]["config"]):
            if "same_language" not in previous:
                previous["same_language"] = _baseline_same_language(previous["config"])
            summary["generation_baseline"] = {k: previous.get(k) for k in
                                              ("config", "n", *BASELINE_KEYS)}
        if "generation_baseline" in summary and not args.no_judge:
            _rejudge_baseline(summary["generation_baseline"], args.pause)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    write_markdown(summary)
    log(f"\nSaved {summary_path} and {RESULTS / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
