"use client";

import { useEffect, useState } from "react";

import { StageBar } from "@/components/chat/retrieval-panel";
import { AblationChart, ArmTable, GateChart } from "@/components/eval/charts";
import { Badge } from "@/components/ui/badge";
import { api, type BaselineKey, type EvalArm, type EvalSummary, type Stats, type TraceSummary } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { formatMs, formatNumber } from "@/lib/utils";

const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);

const CHANGE_ROWS: { key: BaselineKey; label: MessageKey; lowerIsBetter?: boolean }[] = [
  { key: "answer_correct", label: "eval.correct" },
  { key: "same_language", label: "eval.sameLanguage" },
  { key: "faithful", label: "eval.faithful" },
  { key: "citation_grounded", label: "eval.grounded" },
  { key: "unanswerable_refused", label: "eval.find.refusal" },
  { key: "answerable_refused", label: "eval.falseRefusal", lowerIsBetter: true },
];

function BeforeAfter({
  before,
  after,
}: {
  before: Partial<Record<BaselineKey, number | null>>;
  after: Partial<Record<BaselineKey, number | null | undefined>>;
}) {
  const { t } = useI18n();
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="w-full max-w-[640px] text-left text-[13px]">
        <caption className="sr-only">{t("eval.change.title")}</caption>
        <thead>
          <tr className="border-b border-mist text-[12px] text-muted">
            <th className="py-2 pr-3 font-medium">{t("eval.metric")}</th>
            <th className="px-3 py-2 text-right font-medium">{t("eval.change.before")}</th>
            <th className="py-2 pl-3 text-right font-medium">{t("eval.change.after")}</th>
          </tr>
        </thead>
        <tbody>
          {CHANGE_ROWS.map((r) => (
            <tr key={r.key} className="border-b border-mist/70">
              <td className="py-2 pr-3">
                {t(r.label)}
                {r.lowerIsBetter && <span className="text-muted"> ({t("eval.change.lower")})</span>}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-muted">{pct(before[r.key])}</td>
              <td className="py-2 pl-3 text-right font-semibold tabular-nums">{pct(after[r.key])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Figure({ value, label, detail }: { value: string; label: string; detail?: string }) {
  return (
    <div>
      <dd className="font-serif text-[2rem] font-semibold leading-none tabular-nums">{value}</dd>
      <dt className="mt-2 text-[13px] leading-snug text-muted">{label}</dt>
      {detail && <p className="mt-1 text-[12px] text-muted">{detail}</p>}
    </div>
  );
}

function Findings({ s }: { s: EvalSummary }) {
  const { t } = useI18n();
  const arm = (id: string): EvalArm | undefined => s.retrieval?.arms.find((a) => a.id === id);
  const ws = arm("bm25_ws")?.by_type.ko?.["recall@5"];
  const kiwi = arm("bm25_kiwi")?.by_type.ko?.["recall@5"];
  const vec = arm("vector")?.overall["recall@5"];
  const full = arm("hybrid_rerank")?.overall["recall@5"];
  const crossBefore = arm("hybrid_rerank")?.by_type.cross?.["recall@5"];
  const crossAfter = s.generation?.retrieval_with_translation.by_type.cross?.["recall@5"];
  const items: { value: string; label: string; detail?: string }[] = [];
  if (ws != null && kiwi != null) items.push({ value: `${pct(ws)} → ${pct(kiwi)}`, label: t("eval.find.kiwi") });
  if (vec != null && full != null) items.push({ value: `${pct(vec)} → ${pct(full)}`, label: t("eval.find.hybrid") });
  if (crossBefore != null && crossAfter != null)
    items.push({ value: `${pct(crossBefore)} → ${pct(crossAfter)}`, label: t("eval.find.translation") });
  if (s.generation) items.push({ value: pct(s.generation.unanswerable_refused), label: t("eval.find.refusal") });
  if (!items.length) return null;
  return (
    <section className="mt-10">
      <h2 className="text-[17px] font-semibold">{t("eval.findings")}</h2>
      <dl className="mt-5 grid gap-x-8 gap-y-7 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((i) => (
          <Figure key={i.label} {...i} />
        ))}
      </dl>
    </section>
  );
}

export default function EvaluationPage() {
  const { t, locale } = useI18n();
  const [summary, setSummary] = useState<EvalSummary | null | "missing">(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.evaluation().then(setSummary).catch(() => setSummary("missing"));
    Promise.all([api.stats(), api.traces(20)])
      .then(([s, tr]) => {
        setStats(s);
        setTraces(tr);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const timeFmt = new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" });
  const s = summary && summary !== "missing" ? summary : null;
  const by = s?.dataset.by_type ?? {};

  return (
    <main className="mx-auto w-full max-w-[1040px] px-5 py-8 md:px-10">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">{t("eval.title")}</h1>
      <p className="mt-2 max-w-[70ch] text-[15px] text-muted">{t("eval.subtitle")}</p>

      {summary === "missing" && (
        <section className="mt-8 border-l-2 border-celadon pl-5">
          <h2 className="text-[17px] font-semibold">{t("eval.pending.title")}</h2>
          <p className="mt-1 max-w-[70ch] text-[14.5px] text-muted">{t("eval.pending.body")}</p>
          <p className="mt-2 font-mono text-[12.5px] text-muted">{t("eval.run")}</p>
        </section>
      )}

      {s && (
        <>
          <p className="mt-3 text-[13px] text-muted">
            {t("eval.dataset", {
              n: s.dataset.n,
              ko: by.ko ?? 0,
              en: by.en ?? 0,
              cross: (by.cross_en_ko ?? 0) + (by.cross_ko_en ?? 0),
              un: by.unanswerable ?? 0,
              at: s.generated_at,
            })}{" "}
            {s.models.embedder}, {s.models.reranker}, {s.models.llm}.
          </p>

          <Findings s={s} />

          {s.retrieval && (
            <section className="mt-12">
              <h2 className="text-[17px] font-semibold">{t("eval.ablation")}</h2>
              <p className="mt-1 max-w-[72ch] text-[14px] text-muted">{t("eval.ablation.body")}</p>
              <div className="mt-5">
                <AblationChart arms={s.retrieval.arms} />
              </div>
              <div className="mt-6">
                <ArmTable arms={s.retrieval.arms} />
              </div>
            </section>
          )}

          {s.generation && (
            <section className="mt-12">
              <h2 className="text-[17px] font-semibold">{t("eval.answers")}</h2>
              <p className="mt-1 max-w-[72ch] text-[14px] text-muted">{t("eval.answers.body")}</p>
              <dl className="mt-5 grid gap-x-8 gap-y-7 sm:grid-cols-3 lg:grid-cols-5">
                <Figure value={pct(s.generation.answer_correct)} label={t("eval.correct")} />
                <Figure value={pct(s.generation.citation_grounded)} label={t("eval.grounded")} />
                <Figure value={pct(s.generation.faithful)} label={t("eval.faithful")} />
                <Figure value={pct(s.generation.unanswerable_refused)} label={t("eval.find.refusal")} />
                <Figure value={pct(s.generation.answerable_refused)} label={t("eval.falseRefusal")} />
              </dl>
              <h3 className="mb-2 mt-8 text-[13px] font-semibold">
                {t("eval.stageTime")}{" "}
                <span className="font-normal text-muted">({formatMs(s.generation.total_ms.p50)} median)</span>
              </h3>
              <StageBar stages={s.generation.latency_ms} />
            </section>
          )}

          {s.generation && s.generation_baseline && (
            <section className="mt-12">
              <h2 className="text-[17px] font-semibold">{t("eval.change.title")}</h2>
              <p className="mt-1 max-w-[72ch] text-[14px] text-muted">{t("eval.change.body")}</p>
              <BeforeAfter before={s.generation_baseline} after={s.generation} />
            </section>
          )}

          {s.retrieval && (
            <section className="mt-12">
              <h2 className="text-[17px] font-semibold">{t("eval.gate.title")}</h2>
              <p className="mt-1 max-w-[72ch] text-[14px] text-muted">
                {t("eval.gate.body")} {t("eval.gate.current", { v: s.retrieval.refusal_gate.current })}
              </p>
              <div className="mt-4">
                <GateChart gate={s.retrieval.refusal_gate} />
              </div>
            </section>
          )}
        </>
      )}

      {error && <p className="mt-8 rounded-md border border-seal/30 bg-seal-wash px-4 py-3 text-sm text-seal">{error}</p>}

      {stats && (
        <section className="mt-14 border-t border-mist pt-8">
          <h2 className="text-[17px] font-semibold">{t("eval.live")}</h2>
          <dl className="mt-4 grid gap-6 sm:grid-cols-3">
            <Figure value={formatNumber(stats.questions, locale)} label={t("eval.questions")} />
            <Figure value={formatNumber(stats.refusals, locale)} label={t("eval.refusals")} />
            <Figure value={formatMs(stats.avg_latency_ms)} label={t("eval.latency")} />
          </dl>
        </section>
      )}

      {traces.length > 0 && (
        <section className="mt-10">
          <h2 className="text-[17px] font-semibold">{t("eval.recent")}</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-mist text-[12.5px] text-muted">
                  <th className="py-2 pr-4 font-medium">{t("eval.col.question")}</th>
                  <th className="px-4 py-2 font-medium">{t("eval.col.mode")}</th>
                  <th className="px-4 py-2 font-medium">{t("eval.col.result")}</th>
                  <th className="min-w-[220px] py-2 pl-4 font-medium">{t("eval.col.time")}</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((tr) => (
                  <tr key={tr.id} className="border-b border-mist/70 align-top">
                    <td className="py-3 pr-4">
                      <p className="font-medium">{tr.query}</p>
                      <p className="text-[12px] text-muted">{timeFmt.format(new Date(tr.created_at))}</p>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-muted">{t(`chat.mode.${tr.mode}` as MessageKey)}</td>
                    <td className="px-4 py-3">
                      {tr.error && !tr.refused && !tr.answer ? (
                        <Badge variant="seal">{t("eval.failed")}</Badge>
                      ) : (
                        <Badge variant={tr.refused ? "outline" : "default"}>
                          {tr.refused ? t("eval.refused") : t("eval.answered")}
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 pl-4">
                      <p className="mb-1.5 tabular-nums">{formatMs(tr.total_ms)}</p>
                      <StageBar stages={tr.stages_ms} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}
