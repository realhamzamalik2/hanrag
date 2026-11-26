// Typed client for the HanRAG FastAPI backend.

// Empty = same origin: Next.js forwards /api/* to the backend (see next.config.ts).
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");
const API_LABEL = API_URL || "the HanRAG API";

export type Mode = "vector" | "bm25" | "hybrid" | "hybrid_rerank";
export type Tokenizer = "kiwi" | "whitespace";

export interface Passage {
  number?: number | null;
  chunk_id: string;
  document_id: string;
  doc_title: string;
  filename: string;
  page: number;
  section: string;
  text: string;
  char_start: number;
  char_end: number;
  lang: string;
  paginated: boolean;
  score: number;
  rank: number;
  scores: Record<string, number>;
}

export interface DebugItem {
  chunk_id: string;
  document_id: string;
  doc_title: string;
  page: number;
  section: string;
  paginated: boolean;
  lang: string;
  rank: number;
  score: number;
  scores: Record<string, number>;
  text: string;
}

export interface RetrievalDebug {
  query: string;
  extra_queries: string[];
  mode: Mode;
  tokenizer: Tokenizer;
  lists: Record<string, DebugItem[]>;
  fused: DebugItem[];
  reranked: DebugItem[];
  final: DebugItem[];
  stages_ms: Record<string, number>;
}

export interface DocumentInfo {
  id: string;
  filename: string;
  title: string;
  file_type: string;
  lang: string;
  paginated: boolean;
  num_pages: number;
  num_chunks: number;
  num_chars: number;
  status: "pending" | "ready" | "failed";
  error: string | null;
  source_url: string | null;
  license: string | null;
  ingest_ms: number | null;
  created_at: string;
}

export interface ChunkInfo {
  id: string;
  chunk_index: number;
  page: number;
  section: string;
  text: string;
  char_start: number;
  char_end: number;
  lang: string;
}

export interface Job {
  id: string;
  filename: string;
  status: "queued" | "running" | "done" | "failed";
  stage: string;
  progress: number;
  document_id: string | null;
  error: string | null;
  skipped: boolean;
}

export interface Stats {
  documents: number;
  chunks: number;
  pages: number;
  chars: number;
  by_lang: Record<string, number>;
  by_type: Record<string, number>;
  questions: number;
  refusals: number;
  avg_latency_ms: number | null;
}

export interface TraceSummary {
  id: string;
  created_at: string;
  query: string;
  rewritten_query: string | null;
  mode: string;
  answer: string | null;
  refused: boolean;
  model: string | null;
  prompt_tokens: number | null;
  output_tokens: number | null;
  total_ms: number | null;
  stages_ms: Record<string, number>;
  error: string | null;
}

export interface RetrievalMetrics {
  "recall@1": number;
  "recall@3": number;
  "recall@5": number;
  "recall@10": number;
  "mrr@10": number;
  n?: number;
}

export interface EvalArm {
  id: string;
  label: string;
  mode: Mode;
  tokenizer: Tokenizer;
  overall: RetrievalMetrics;
  by_type: Record<string, RetrievalMetrics>;
  latency_ms: { mean: number; p50: number; p95: number };
}

export interface EvalSummary {
  generated_at: string;
  dataset: { n: number; by_type: Record<string, number> };
  models: { embedder: string; reranker: string; llm: string };
  retrieval?: {
    arms: EvalArm[];
    refusal_gate: {
      current: number;
      sweep: { threshold: number; unanswerable_refused: number; answerable_refused: number }[];
    };
  };
  generation?: {
    n: number;
    answer_correct: number;
    answer_correct_when_answered: number;
    citation_grounded: number;
    faithful: number | null;
    judged: number;
    same_language?: number;
    unanswerable_refused: number;
    answerable_refused: number;
    by_type: Record<string, { n: number; correct?: number; refused: number }>;
    latency_ms: Record<string, number>;
    total_ms: { mean: number; p50: number; p95: number };
    retrieval_with_translation: RetrievalMetrics & { by_type: Record<string, RetrievalMetrics> };
  };
  /** First run before the error-analysis fixes, kept for a before/after comparison. */
  generation_baseline?: Partial<Record<BaselineKey, number | null>> & { n: number };
}

export type BaselineKey =
  | "answer_correct"
  | "faithful"
  | "citation_grounded"
  | "same_language"
  | "unanswerable_refused"
  | "answerable_refused";

export interface Health {
  status: string;
  database: boolean;
  models_ready: boolean;
  llm_configured: boolean;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface ChatOptions {
  mode?: Mode;
  tokenizer?: Tokenizer;
  rewrite?: boolean;
  k?: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, `Can't reach ${API_LABEL}. Start it with scripts\\run_api.ps1.`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Stats>("/api/stats"),
  documents: () => request<DocumentInfo[]>("/api/documents"),
  document: (id: string) => request<DocumentInfo>(`/api/documents/${id}`),
  chunks: (id: string, page?: number) =>
    request<ChunkInfo[]>(`/api/documents/${id}/chunks${page != null ? `?page=${page}` : ""}`),
  fileUrl: (id: string) => `${API_URL}/api/documents/${id}/file`,
  deleteDocument: (id: string) => request<void>(`/api/documents/${id}`, { method: "DELETE" }),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Job>("/api/documents", { method: "POST", body: form });
  },
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  traces: (limit = 30) => request<TraceSummary[]>(`/api/traces?limit=${limit}`),
  evaluation: () => request<EvalSummary>("/api/eval"),
};

// ---- Streaming chat (Server-Sent Events over POST) ----

export type StreamEvent =
  | { type: "rewrite"; standalone: string; translation: string | null }
  | { type: "retrieval"; retrieval: RetrievalDebug; passages: Passage[] }
  | { type: "token"; text: string }
  | {
      type: "done";
      refused: boolean;
      refusal_reason: string | null;
      answer?: string;
      citations: Passage[];
      trace_id: string | null;
      stages_ms: Record<string, number>;
      total_ms: number;
    }
  | { type: "error"; message: string };

export async function streamChat(
  question: string,
  history: ChatTurn[],
  options: ChatOptions,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify({ question, history, ...options }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    throw new ApiError(0, `Can't reach ${API_LABEL}. Start it with scripts\\run_api.ps1.`);
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const data = raw
        .split("\n")
        .filter((l) => l.startsWith("data:"))
        .map((l) => l.slice(5).replace(/^ /, ""))
        .join("\n");
      if (!data) continue; // comments / pings
      try {
        onEvent(JSON.parse(data) as StreamEvent);
      } catch {
        /* ignore malformed event */
      }
    }
  }
}
