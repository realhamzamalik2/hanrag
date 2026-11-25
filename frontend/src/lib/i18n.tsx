"use client";

import { createContext, useCallback, useContext, useEffect, useSyncExternalStore, type ReactNode } from "react";

export type Locale = "ko" | "en";

const en = {
  "nav.chat": "Ask",
  "nav.documents": "Documents",
  "nav.eval": "Evaluation",
  "nav.api": "API docs",
  "app.tagline": "Answers from your Korean and English documents, every claim cited.",
  "theme.toggle": "Switch light or dark mode",
  "lang.toggle": "한국어로 보기",

  "chat.placeholder": "Ask about your documents, in Korean or English",
  "chat.send": "Ask",
  "chat.stop": "Stop",
  "chat.new": "New conversation",
  "chat.empty.title": "Ask a question in either language",
  "chat.empty.body":
    "HanRAG searches your documents by keyword and by meaning, reranks the passages, and answers only from what it found. Each claim links to the page it came from.",
  "chat.empty.try": "Try one of these",
  "chat.stage.rewrite": "Understanding the question",
  "chat.stage.retrieve": "Searching documents",
  "chat.stage.generate": "Writing the answer",
  "chat.refused": "Not in your documents",
  "chat.sources": "Sources",
  "chat.howFound": "How I found this",
  "chat.searchedAs": "Searched as",
  "chat.alsoSearched": "Also searched in translation",
  "chat.latency": "Time per step",
  "chat.error": "Something went wrong",
  "chat.retry": "Ask again",
  "chat.settings": "Search settings",
  "chat.mode": "Retrieval",
  "chat.mode.hybrid_rerank": "Hybrid + reranker",
  "chat.mode.hybrid": "Hybrid",
  "chat.mode.vector": "Meaning only",
  "chat.mode.bm25": "Keywords only",
  "chat.tokenizer": "Korean keyword tokens",
  "chat.tokenizer.kiwi": "Morphemes (Kiwi)",
  "chat.tokenizer.whitespace": "Spaces only",
  "chat.rewrite": "Rewrite and translate the question",
  "chat.rewrite.hint": "Uses one extra AI call per question",

  "debug.keyword": "Keyword search",
  "debug.keyword.hint": "BM25 on Korean morphemes",
  "debug.meaning": "Meaning search",
  "debug.meaning.hint": "bge-m3 vectors, cross-lingual",
  "debug.final": "After reranking",
  "debug.final.hint": "Cross-encoder reads question and passage together",
  "debug.fused": "Merged ranking",
  "debug.fused.hint": "Reciprocal Rank Fusion of both lists",
  "debug.was": "was #{n}",
  "debug.new": "new",
  "debug.used": "Given to the answer",
  "debug.none": "No matches",
  "stage.rewrite": "Rewrite",
  "stage.retrieve_bm25": "Keywords",
  "stage.retrieve_vector": "Meaning",
  "stage.retrieve_fusion": "Merge",
  "stage.retrieve_rerank": "Rerank",
  "stage.generate": "Answer",

  "source.page": "Page {n}",
  "source.part": "Part {n}",
  "source.openFull": "Open document",
  "source.close": "Close",
  "source.loading": "Loading page",
  "source.cited": "Cited passage",
  "source.license": "Source and license",

  "docs.title": "Documents",
  "docs.subtitle": "Upload PDF, Word, text, Markdown or Hangul (HWP, HWPX) files. They are split into passages and indexed for search.",
  "docs.drop": "Drop files here or choose files",
  "docs.drop.hint": "Up to 50 MB each. Scanned PDFs without text are not supported yet.",
  "docs.choose": "Choose files",
  "docs.empty": "No documents yet. Upload one above, or run scripts.fetch_samples to add the demo set.",
  "docs.col.title": "Document",
  "docs.col.lang": "Language",
  "docs.col.pages": "Pages",
  "docs.col.chunks": "Passages",
  "docs.col.added": "Added",
  "docs.delete": "Delete",
  "docs.delete.confirm": "Delete “{name}”? Its passages are removed from search. This can't be undone.",
  "docs.deleted": "Deleted {name}",
  "docs.job.queued": "Waiting",
  "docs.job.parsing": "Reading",
  "docs.job.chunking": "Splitting into passages",
  "docs.job.embedding": "Indexing",
  "docs.job.done": "Ready",
  "docs.job.skipped": "Already indexed",
  "docs.job.failed": "Failed",
  "docs.stat.documents": "documents",
  "docs.stat.pages": "pages",
  "docs.stat.chunks": "passages",
  "lang.ko": "Korean",
  "lang.en": "English",
  "lang.mixed": "Mixed",

  "eval.title": "Evaluation",
  "eval.subtitle": "How well retrieval and answers work, measured on a fixed question set, plus live numbers from real questions.",
  "eval.pending.title": "Benchmark results arrive in the next build step",
  "eval.pending.body":
    "50 Korean and English questions (some deliberately unanswerable) will compare keyword, meaning, hybrid and hybrid + reranker search, and Kiwi against plain spaces.",
  "eval.live": "Live usage",
  "eval.questions": "Questions answered",
  "eval.refusals": "Refused as not in documents",
  "eval.latency": "Average time per question",
  "eval.recent": "Recent questions",
  "eval.col.question": "Question",
  "eval.col.mode": "Retrieval",
  "eval.col.time": "Time",
  "eval.col.result": "Result",
  "eval.answered": "Answered",
  "eval.refused": "Refused",
  "eval.failed": "Failed",
  "eval.metric": "Metric",
  "eval.medianLatency": "Median time",
  "eval.bestValue": "Best: {v}. Bars show the share of answerable questions whose evidence passage was retrieved.",
  "eval.threshold": "Threshold",
  "eval.gate.title": "When to refuse before calling the LLM",
  "eval.gate.body": "If the reranker's best score is below a threshold, HanRAG refuses immediately. Higher thresholds catch more unanswerable questions but start rejecting answerable ones.",
  "eval.gate.current": "Current threshold: {v}",
  "eval.gate.unanswerable": "Unanswerable refused",
  "eval.gate.answerable": "Answerable wrongly refused",
  "eval.group.ko": "Korean",
  "eval.group.en": "English",
  "eval.group.cross": "Cross-lingual",
  "eval.ablation": "Retrieval ablation",
  "eval.ablation.body": "Each configuration retrieves the top 10 passages for the 40 answerable questions. A hit means a retrieved passage contains the question's evidence sentence. No LLM is involved.",
  "eval.col.config": "Configuration",
  "eval.findings": "Key findings",
  "eval.find.kiwi": "Korean keyword search with Kiwi morphemes vs plain spaces (Recall@5)",
  "eval.find.hybrid": "Hybrid + reranker vs meaning search alone (Recall@5)",
  "eval.find.translation": "Cross-lingual questions found with query translation (Recall@5)",
  "eval.find.refusal": "Unanswerable questions correctly refused",
  "eval.answers": "Answer quality",
  "eval.answers.body": "The default pipeline answered all 50 questions through Gemini. Faithfulness was judged by the same model, so treat it as an indicator, not ground truth.",
  "eval.correct": "Answers with all required facts",
  "eval.grounded": "Answers citing the evidence passage",
  "eval.faithful": "Answers fully supported by their citations",
  "eval.falseRefusal": "Answerable questions refused",
  "eval.stageTime": "Average time per step",
  "eval.dataset": "{n} questions: {ko} Korean, {en} English, {cross} cross-lingual, {un} unanswerable. Generated {at}.",
  "eval.run": "Run the benchmark with: cd backend; uv run python -m scripts.run_eval",

  "api.offline": "The HanRAG API isn't running. Start it with scripts\\run_api.ps1, then reload.",
  "api.warming": "Loading search models. The first answer may take a little longer.",
} as const;

export type MessageKey = keyof typeof en;

const ko: Record<MessageKey, string> = {
  "nav.chat": "질문하기",
  "nav.documents": "문서",
  "nav.eval": "평가",
  "nav.api": "API 문서",
  "app.tagline": "한국어와 영어 문서에서 찾은 답, 모든 주장에 출처를 붙입니다.",
  "theme.toggle": "밝은 화면 또는 어두운 화면으로 전환",
  "lang.toggle": "View in English",

  "chat.placeholder": "문서에 대해 한국어나 영어로 질문하세요",
  "chat.send": "질문",
  "chat.stop": "중지",
  "chat.new": "새 대화",
  "chat.empty.title": "어느 언어로든 질문하세요",
  "chat.empty.body":
    "HanRAG는 키워드와 의미로 문서를 검색하고, 찾은 구절을 다시 순위 매긴 뒤, 찾은 내용만으로 답합니다. 각 주장은 출처 페이지로 연결됩니다.",
  "chat.empty.try": "이런 질문을 해 보세요",
  "chat.stage.rewrite": "질문을 이해하는 중",
  "chat.stage.retrieve": "문서를 검색하는 중",
  "chat.stage.generate": "답변을 작성하는 중",
  "chat.refused": "문서에 없는 내용",
  "chat.sources": "출처",
  "chat.howFound": "이렇게 찾았습니다",
  "chat.searchedAs": "검색한 질문",
  "chat.alsoSearched": "번역해서 함께 검색",
  "chat.latency": "단계별 시간",
  "chat.error": "문제가 발생했습니다",
  "chat.retry": "다시 질문",
  "chat.settings": "검색 설정",
  "chat.mode": "검색 방식",
  "chat.mode.hybrid_rerank": "하이브리드 + 재순위",
  "chat.mode.hybrid": "하이브리드",
  "chat.mode.vector": "의미 검색만",
  "chat.mode.bm25": "키워드 검색만",
  "chat.tokenizer": "한국어 키워드 분석",
  "chat.tokenizer.kiwi": "형태소 (Kiwi)",
  "chat.tokenizer.whitespace": "띄어쓰기만",
  "chat.rewrite": "질문 다시 쓰기와 번역",
  "chat.rewrite.hint": "질문마다 AI 호출이 한 번 더 필요합니다",

  "debug.keyword": "키워드 검색",
  "debug.keyword.hint": "한국어 형태소 기반 BM25",
  "debug.meaning": "의미 검색",
  "debug.meaning.hint": "bge-m3 벡터, 언어 간 검색",
  "debug.final": "재순위 후",
  "debug.final.hint": "질문과 구절을 함께 읽는 크로스 인코더",
  "debug.fused": "합친 순위",
  "debug.fused.hint": "두 목록의 RRF(Reciprocal Rank Fusion)",
  "debug.was": "이전 #{n}",
  "debug.new": "신규",
  "debug.used": "답변에 사용됨",
  "debug.none": "결과 없음",
  "stage.rewrite": "다시 쓰기",
  "stage.retrieve_bm25": "키워드",
  "stage.retrieve_vector": "의미",
  "stage.retrieve_fusion": "합치기",
  "stage.retrieve_rerank": "재순위",
  "stage.generate": "답변",

  "source.page": "{n}쪽",
  "source.part": "{n}부분",
  "source.openFull": "문서 열기",
  "source.close": "닫기",
  "source.loading": "페이지를 불러오는 중",
  "source.cited": "인용된 구절",
  "source.license": "출처와 라이선스",

  "docs.title": "문서",
  "docs.subtitle": "PDF, Word, 텍스트, 마크다운, 한글(HWP, HWPX) 파일을 올리세요. 구절로 나누어 검색할 수 있게 색인합니다.",
  "docs.drop": "파일을 여기에 놓거나 선택하세요",
  "docs.drop.hint": "파일당 최대 50MB. 텍스트가 없는 스캔 PDF는 아직 지원하지 않습니다.",
  "docs.choose": "파일 선택",
  "docs.empty": "아직 문서가 없습니다. 위에서 올리거나 scripts.fetch_samples로 데모 문서를 추가하세요.",
  "docs.col.title": "문서",
  "docs.col.lang": "언어",
  "docs.col.pages": "페이지",
  "docs.col.chunks": "구절",
  "docs.col.added": "추가일",
  "docs.delete": "삭제",
  "docs.delete.confirm": "“{name}” 문서를 삭제할까요? 검색에서 구절이 제거되며 되돌릴 수 없습니다.",
  "docs.deleted": "{name} 삭제됨",
  "docs.job.queued": "대기 중",
  "docs.job.parsing": "읽는 중",
  "docs.job.chunking": "구절로 나누는 중",
  "docs.job.embedding": "색인하는 중",
  "docs.job.done": "완료",
  "docs.job.skipped": "이미 색인됨",
  "docs.job.failed": "실패",
  "docs.stat.documents": "개 문서",
  "docs.stat.pages": "쪽",
  "docs.stat.chunks": "개 구절",
  "lang.ko": "한국어",
  "lang.en": "영어",
  "lang.mixed": "혼합",

  "eval.title": "평가",
  "eval.subtitle": "고정된 질문 세트로 측정한 검색과 답변 품질, 그리고 실제 질문에서 나온 실시간 수치입니다.",
  "eval.pending.title": "벤치마크 결과는 다음 단계에서 추가됩니다",
  "eval.pending.body":
    "한국어와 영어 질문 50개(일부는 일부러 답이 없는 질문)로 키워드, 의미, 하이브리드, 하이브리드 + 재순위 검색과 Kiwi 대 띄어쓰기를 비교합니다.",
  "eval.live": "실시간 사용 현황",
  "eval.questions": "답변한 질문",
  "eval.refusals": "문서에 없어 거절한 질문",
  "eval.latency": "질문당 평균 시간",
  "eval.recent": "최근 질문",
  "eval.col.question": "질문",
  "eval.col.mode": "검색 방식",
  "eval.col.time": "시간",
  "eval.col.result": "결과",
  "eval.answered": "답변",
  "eval.refused": "거절",
  "eval.failed": "실패",
  "eval.metric": "지표",
  "eval.medianLatency": "중앙값 시간",
  "eval.bestValue": "최고값: {v}. 막대는 근거 구절을 찾아낸 답변 가능 질문의 비율입니다.",
  "eval.threshold": "임계값",
  "eval.gate.title": "LLM 호출 전에 언제 거절할까",
  "eval.gate.body": "재순위 모델의 최고 점수가 임계값보다 낮으면 HanRAG는 바로 거절합니다. 임계값을 높이면 답이 없는 질문을 더 많이 거르지만, 답할 수 있는 질문도 거절하기 시작합니다.",
  "eval.gate.current": "현재 임계값: {v}",
  "eval.gate.unanswerable": "답 없는 질문 거절",
  "eval.gate.answerable": "답 있는 질문 잘못 거절",
  "eval.group.ko": "한국어",
  "eval.group.en": "영어",
  "eval.group.cross": "언어 간",
  "eval.ablation": "검색 방식 비교 (Ablation)",
  "eval.ablation.body": "각 설정이 답변 가능한 질문 40개에 대해 상위 10개 구절을 검색합니다. 검색된 구절에 질문의 근거 문장이 있으면 적중입니다. LLM은 사용하지 않습니다.",
  "eval.col.config": "설정",
  "eval.findings": "주요 결과",
  "eval.find.kiwi": "Kiwi 형태소 대 띄어쓰기 기반 한국어 키워드 검색 (Recall@5)",
  "eval.find.hybrid": "하이브리드 + 재순위 대 의미 검색 단독 (Recall@5)",
  "eval.find.translation": "질문 번역으로 찾은 언어 간 질문 (Recall@5)",
  "eval.find.refusal": "답 없는 질문을 올바르게 거절",
  "eval.answers": "답변 품질",
  "eval.answers.body": "기본 파이프라인이 Gemini로 50개 질문 모두에 답했습니다. 충실도는 같은 모델이 판정했으므로 참고 지표로 보세요.",
  "eval.correct": "필수 사실을 모두 포함한 답변",
  "eval.grounded": "근거 구절을 인용한 답변",
  "eval.faithful": "인용으로 완전히 뒷받침되는 답변",
  "eval.falseRefusal": "답할 수 있는데 거절한 질문",
  "eval.stageTime": "단계별 평균 시간",
  "eval.dataset": "질문 {n}개: 한국어 {ko}, 영어 {en}, 언어 간 {cross}, 답 없음 {un}. {at} 생성.",
  "eval.run": "벤치마크 실행: cd backend; uv run python -m scripts.run_eval",

  "api.offline": "HanRAG API가 실행되고 있지 않습니다. scripts\\run_api.ps1로 시작한 뒤 새로고침하세요.",
  "api.warming": "검색 모델을 불러오는 중입니다. 첫 답변은 조금 더 걸릴 수 있습니다.",
};

const dictionaries: Record<Locale, Record<MessageKey, string>> = { en, ko };

interface I18n {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18n | null>(null);

const LOCALE_KEY = "hanrag.locale";
const localeListeners = new Set<() => void>();

function readLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_KEY);
    if (saved === "ko" || saved === "en") return saved;
  } catch {
    /* storage unavailable */
  }
  return navigator.language.toLowerCase().startsWith("ko") ? "ko" : "en";
}

function subscribeLocale(cb: () => void) {
  localeListeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    localeListeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore<Locale>(subscribeLocale, readLocale, () => "ko");

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    try {
      localStorage.setItem(LOCALE_KEY, l);
    } catch {
      /* ignore */
    }
    localeListeners.forEach((cb) => cb());
  }, []);

  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => {
      let s: string = dictionaries[locale][key] ?? en[key] ?? key;
      if (vars) for (const [k, v] of Object.entries(vars)) s = s.replaceAll(`{${k}}`, String(v));
      return s;
    },
    [locale],
  );

  return <I18nContext.Provider value={{ locale, setLocale, t }}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used inside I18nProvider");
  return ctx;
}
