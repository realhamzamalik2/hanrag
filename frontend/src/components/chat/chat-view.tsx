"use client";

import { ChevronDown, Loader2, RotateCcw, Send, SlidersHorizontal, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { AnswerText } from "@/components/chat/answer-text";
import { RetrievalPanel } from "@/components/chat/retrieval-panel";
import { SourceViewer, sourceLocation, type SourceRef } from "@/components/source-viewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  streamChat,
  type ChatOptions,
  type ChatTurn,
  type Mode,
  type Passage,
  type RetrievalDebug,
  type Tokenizer,
} from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { cn, formatMs } from "@/lib/utils";

type Stage = "rewrite" | "retrieve" | "generate" | "done" | "error";

interface UserMessage {
  id: string;
  role: "user";
  text: string;
}

interface AssistantMessage {
  id: string;
  role: "assistant";
  question: string;
  stage: Stage;
  text: string;
  refused: boolean;
  passages: Passage[];
  citedNumbers: number[];
  retrieval: RetrievalDebug | null;
  stages: Record<string, number>;
  totalMs: number | null;
  error: string | null;
}

type Message = UserMessage | AssistantMessage;

const SAMPLE_QUESTIONS = [
  "한글은 누가, 언제 만들었나요?",
  "Who created Hangul, and when was it published?",
  "경복궁은 언제 지어졌나요?",
  "What is retrieval-augmented generation?",
  "김치는 어떻게 만드나요?",
];

const DEFAULT_OPTIONS: Required<Pick<ChatOptions, "mode" | "tokenizer" | "rewrite">> = {
  mode: "hybrid_rerank",
  tokenizer: "kiwi",
  rewrite: true,
};

const uid = () => Math.random().toString(36).slice(2, 10);

function toRef(p: Passage): SourceRef {
  return {
    document_id: p.document_id,
    doc_title: p.doc_title,
    page: p.page,
    paginated: p.paginated,
    section: p.section,
    chunk_id: p.chunk_id,
    text: p.text,
  };
}

function SettingsPopover({
  options,
  onChange,
}: {
  options: typeof DEFAULT_OPTIONS;
  onChange: (o: typeof DEFAULT_OPTIONS) => void;
}) {
  const { t } = useI18n();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm" className="text-muted">
          <SlidersHorizontal />
          {t(`chat.mode.${options.mode}` as MessageKey)}
          <ChevronDown className="opacity-60" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="space-y-4">
        <h3 className="text-sm font-semibold">{t("chat.settings")}</h3>
        <label className="block space-y-1.5">
          <span className="text-[13px] text-muted">{t("chat.mode")}</span>
          <Select value={options.mode} onValueChange={(v) => onChange({ ...options, mode: v as Mode })}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(["hybrid_rerank", "hybrid", "vector", "bm25"] as const).map((m) => (
                <SelectItem key={m} value={m}>
                  {t(`chat.mode.${m}`)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        <label className="block space-y-1.5">
          <span className="text-[13px] text-muted">{t("chat.tokenizer")}</span>
          <Select
            value={options.tokenizer}
            onValueChange={(v) => onChange({ ...options, tokenizer: v as Tokenizer })}
            disabled={options.mode === "vector"}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="kiwi">{t("chat.tokenizer.kiwi")}</SelectItem>
              <SelectItem value="whitespace">{t("chat.tokenizer.whitespace")}</SelectItem>
            </SelectContent>
          </Select>
        </label>
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[13px]">{t("chat.rewrite")}</p>
            <p className="text-[12px] text-muted">{t("chat.rewrite.hint")}</p>
          </div>
          <Switch checked={options.rewrite} onCheckedChange={(v) => onChange({ ...options, rewrite: v })} />
        </div>
      </PopoverContent>
    </Popover>
  );
}

function StageLine({ stage }: { stage: Stage }) {
  const { t } = useI18n();
  const key: Record<string, MessageKey> = {
    rewrite: "chat.stage.rewrite",
    retrieve: "chat.stage.retrieve",
    generate: "chat.stage.generate",
  };
  if (!(stage in key)) return null;
  return (
    <p className="flex items-center gap-2 text-[13px] text-muted" role="status">
      <Loader2 className="size-3.5 animate-spin" />
      {t(key[stage])}
    </p>
  );
}

function AssistantBlock({
  msg,
  onOpenSource,
  activeCitation,
  onRetry,
}: {
  msg: AssistantMessage;
  onOpenSource: (ref: SourceRef, n?: number) => void;
  activeCitation: { msgId: string; n: number } | null;
  onRetry: () => void;
}) {
  const { t } = useI18n();
  const [showDebug, setShowDebug] = useState(false);
  const streaming = msg.stage === "generate" && msg.text.length > 0;
  const cited = msg.citedNumbers
    .map((n) => ({ n, p: msg.passages[n - 1] }))
    .filter((c): c is { n: number; p: Passage } => Boolean(c.p));
  const openCitation = (n: number) => {
    const p = msg.passages[n - 1];
    if (p) onOpenSource(toRef(p), n);
  };

  return (
    <div className="space-y-4">
      {msg.stage !== "done" && msg.stage !== "error" && !streaming && <StageLine stage={msg.stage} />}

      {msg.error ? (
        <div className="rounded-md border border-seal/30 bg-seal-wash px-4 py-3 text-sm text-seal">
          <p className="font-medium">{t("chat.error")}</p>
          <p className="mt-1">{msg.error}</p>
          <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}>
            <RotateCcw /> {t("chat.retry")}
          </Button>
        </div>
      ) : msg.refused ? (
        <div className="max-w-[68ch] border-l-2 border-mist pl-4">
          <Badge variant="outline" className="mb-2">
            {t("chat.refused")}
          </Badge>
          <p className="prose-reading text-muted">{msg.text}</p>
        </div>
      ) : (
        msg.text && (
          <AnswerText
            text={msg.text}
            streaming={streaming}
            activeCitation={activeCitation?.msgId === msg.id ? activeCitation.n : null}
            onCite={openCitation}
            citeLabel={(n) => `${t("chat.sources")} ${n}`}
          />
        )
      )}

      {cited.length > 0 && (
        <section aria-label={t("chat.sources")}>
          <h3 className="mb-2 text-[13px] font-semibold text-muted">{t("chat.sources")}</h3>
          <ul className="grid gap-2 sm:grid-cols-2">
            {cited.map(({ n, p }) => (
              <li key={n}>
                <button
                  type="button"
                  onClick={() => openCitation(n)}
                  className="flex w-full gap-3 rounded-md border border-mist bg-surface p-3 text-left transition-colors hover:border-celadon"
                >
                  <span className="seal pointer-events-none !m-0 !text-[12px]">{n}</span>
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-medium">
                      {p.doc_title} <span className="font-normal text-muted">{sourceLocation(p, t)}</span>
                    </span>
                    <span className="mt-0.5 line-clamp-2 font-serif text-[13px] leading-relaxed text-muted">{p.text}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {msg.retrieval && (msg.stage === "done" || msg.stage === "generate") && (
        <div>
          <button
            type="button"
            onClick={() => setShowDebug((s) => !s)}
            aria-expanded={showDebug}
            className="inline-flex items-center gap-1.5 text-[13px] font-medium text-celadon-deep hover:underline"
          >
            <ChevronDown className={cn("size-4 transition-transform", showDebug && "rotate-180")} />
            {t("chat.howFound")}
            {msg.totalMs != null && <span className="font-normal text-muted">({formatMs(msg.totalMs)})</span>}
          </button>
          {showDebug && (
            <div className="mt-3">
              <RetrievalPanel retrieval={msg.retrieval} stages={msg.stages} onOpen={(ref) => onOpenSource(ref)} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatView() {
  const { t } = useI18n();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [options, setOptions] = useState(DEFAULT_OPTIONS);
  const [source, setSource] = useState<SourceRef | null>(null);
  const [activeCitation, setActiveCitation] = useState<{ msgId: string; n: number } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    try {
      const saved = localStorage.getItem("hanrag.options");
      if (saved) setOptions({ ...DEFAULT_OPTIONS, ...JSON.parse(saved) });
    } catch {
      /* ignore */
    }
  }, []);
  const updateOptions = (o: typeof DEFAULT_OPTIONS) => {
    setOptions(o);
    try {
      localStorage.setItem("hanrag.options", JSON.stringify(o));
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messages.length]);

  const patch = (id: string, fn: (m: AssistantMessage) => Partial<AssistantMessage>) =>
    setMessages((ms) => ms.map((m) => (m.id === id && m.role === "assistant" ? { ...m, ...fn(m) } : m)));

  const ask = useCallback(
    async (question: string, priorMessages: Message[]) => {
      const q = question.trim();
      if (!q || busy) return;
      const history: ChatTurn[] = priorMessages
        .filter((m) => m.role === "user" || (m.role === "assistant" && m.stage === "done" && !m.refused))
        .map((m): ChatTurn => ({ role: m.role, content: m.text }))
        .slice(-8);
      const aId = uid();
      const assistant: AssistantMessage = {
        id: aId,
        role: "assistant",
        question: q,
        stage: options.rewrite ? "rewrite" : "retrieve",
        text: "",
        refused: false,
        passages: [],
        citedNumbers: [],
        retrieval: null,
        stages: {},
        totalMs: null,
        error: null,
      };
      setMessages([...priorMessages, { id: uid(), role: "user", text: q }, assistant]);
      setInput("");
      setBusy(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        await streamChat(
          q,
          history,
          options,
          (e) => {
            if (e.type === "rewrite") patch(aId, () => ({ stage: "retrieve" }));
            else if (e.type === "retrieval")
              patch(aId, () => ({ stage: "generate", retrieval: e.retrieval, passages: e.passages }));
            else if (e.type === "token") patch(aId, (m) => ({ text: m.text + e.text }));
            else if (e.type === "done")
              patch(aId, (m) => ({
                stage: "done",
                refused: e.refused,
                text: e.answer ?? m.text,
                citedNumbers: e.citations.map((c) => c.number ?? 0).filter(Boolean),
                stages: e.stages_ms,
                totalMs: e.total_ms,
              }));
            else if (e.type === "error") patch(aId, () => ({ stage: "error", error: e.message }));
          },
          controller.signal,
        );
        patch(aId, (m) => (m.stage === "done" || m.stage === "error" ? {} : { stage: "done" }));
      } catch (err) {
        patch(aId, () => ({ stage: "error", error: (err as Error).message }));
      } finally {
        setBusy(false);
        abortRef.current = null;
        inputRef.current?.focus();
      }
    },
    [busy, options],
  );

  const submit = () => ask(input, messages);
  const stop = () => abortRef.current?.abort();
  const reset = () => {
    stop();
    setMessages([]);
    setActiveCitation(null);
  };

  const openSource = (ref: SourceRef, n?: number, msgId?: string) => {
    setSource(ref);
    setActiveCitation(n && msgId ? { msgId, n } : null);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[860px] px-5 pb-10 pt-8 md:px-10">
          {messages.length === 0 ? (
            <div className="pt-[8vh]">
              <h1 className="max-w-[18ch] font-serif text-[clamp(1.9rem,4vw,2.75rem)] font-semibold leading-[1.2] tracking-tight">
                {t("chat.empty.title")}
              </h1>
              <p className="mt-4 max-w-[60ch] text-[15.5px] leading-relaxed text-muted">{t("chat.empty.body")}</p>
              <h2 className="mt-10 text-[13px] font-semibold text-muted">{t("chat.empty.try")}</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                {SAMPLE_QUESTIONS.map((q) => (
                  <li key={q}>
                    <button
                      type="button"
                      onClick={() => ask(q, [])}
                      className="rounded-full border border-mist bg-surface px-3.5 py-1.5 text-[14px] transition-colors hover:border-celadon hover:text-celadon-deep"
                    >
                      {q}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <div className="space-y-8">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="border-t border-mist pt-6 first:border-t-0 first:pt-0">
                    <p className="text-[17px] font-semibold leading-snug">{m.text}</p>
                  </div>
                ) : (
                  <AssistantBlock
                    key={m.id}
                    msg={m}
                    activeCitation={activeCitation}
                    onOpenSource={(ref, n) => openSource(ref, n, m.id)}
                    onRetry={() => {
                      const idx = messages.findIndex((x) => x.id === m.id);
                      ask(m.question, messages.slice(0, Math.max(0, idx - 1)));
                    }}
                  />
                ),
              )}
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <div className="border-t border-mist bg-paper/90 backdrop-blur">
        <form
          className="mx-auto w-full max-w-[860px] px-5 py-3 md:px-10"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <div className="rounded-lg border border-mist bg-surface focus-within:border-celadon">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={2}
              placeholder={t("chat.placeholder")}
              aria-label={t("chat.placeholder")}
              className="block w-full resize-none bg-transparent px-4 pt-3 text-[15px] leading-relaxed outline-none placeholder:text-muted"
            />
            <div className="flex items-center justify-between gap-2 px-2 pb-2">
              <div className="flex items-center gap-1">
                <SettingsPopover options={options} onChange={updateOptions} />
                {messages.length > 0 && (
                  <Button type="button" variant="ghost" size="sm" className="text-muted" onClick={reset}>
                    {t("chat.new")}
                  </Button>
                )}
              </div>
              {busy ? (
                <Button type="button" variant="outline" size="sm" onClick={stop}>
                  <Square className="size-3.5" /> {t("chat.stop")}
                </Button>
              ) : (
                <Button type="submit" size="sm" disabled={!input.trim()}>
                  <Send /> {t("chat.send")}
                </Button>
              )}
            </div>
          </div>
        </form>
      </div>

      <Sheet open={source !== null} onOpenChange={(o) => !o && (setSource(null), setActiveCitation(null))}>
        <SheetContent closeLabel={t("source.close")}>
          <SheetTitle className="sr-only">{source?.doc_title}</SheetTitle>
          <SheetDescription className="sr-only">{t("source.cited")}</SheetDescription>
          {source && <SourceViewer key={`${source.chunk_id}-${source.page}`} source={source} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}


