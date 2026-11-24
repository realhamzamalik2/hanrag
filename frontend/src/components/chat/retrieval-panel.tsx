"use client";

import { ArrowDown, ArrowUp } from "lucide-react";

import type { SourceRef } from "@/components/source-viewer";
import { sourceLocation } from "@/components/source-viewer";
import { Tooltip } from "@/components/ui/tooltip";
import type { DebugItem, RetrievalDebug } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { cn, formatMs } from "@/lib/utils";

const COLUMN_SIZE = 8;

function toRef(item: DebugItem): SourceRef {
  return {
    document_id: item.document_id,
    doc_title: item.doc_title,
    page: item.page,
    paginated: item.paginated,
    section: item.section,
    chunk_id: item.chunk_id,
    text: item.text,
  };
}

/** Merge the original-query list and its translated-query list (keep each chunk's best rank). */
function mergeLists(lists: Record<string, DebugItem[]>, prefix: string): DebugItem[] {
  const seen = new Map<string, DebugItem>();
  for (const [name, items] of Object.entries(lists)) {
    if (name !== prefix && !name.startsWith(`${prefix}:`)) continue;
    for (const it of items) {
      const prev = seen.get(it.chunk_id);
      if (!prev || it.score > prev.score) seen.set(it.chunk_id, it);
    }
  }
  return [...seen.values()].sort((a, b) => b.score - a.score).map((it, i) => ({ ...it, rank: i + 1 }));
}

function Column({
  title,
  hint,
  items,
  usedIds,
  format,
  showMovement,
  onOpen,
}: {
  title: MessageKey;
  hint: MessageKey;
  items: DebugItem[];
  usedIds: Set<string>;
  format: (n: number) => string;
  showMovement?: boolean;
  onOpen: (ref: SourceRef) => void;
}) {
  const { t } = useI18n();
  const max = Math.max(...items.map((i) => i.score), 1e-9);
  return (
    <section className="min-w-0">
      <h4 className="text-[13px] font-semibold">{t(title)}</h4>
      <p className="mb-2 text-[12px] text-muted">{t(hint)}</p>
      {items.length === 0 ? (
        <p className="py-3 text-[12.5px] text-muted">{t("debug.none")}</p>
      ) : (
        <ol className="space-y-1">
          {items.slice(0, COLUMN_SIZE).map((it) => {
            const used = usedIds.has(it.chunk_id);
            const was = it.scores.fused_rank;
            const moved = showMovement && typeof was === "number" ? was - it.rank : 0;
            return (
              <li key={it.chunk_id}>
                <button
                  type="button"
                  onClick={() => onOpen(toRef(it))}
                  className={cn(
                    "group w-full rounded-md border border-transparent px-2 py-1.5 text-left transition-colors hover:border-mist hover:bg-surface",
                    used && "bg-surface",
                  )}
                >
                  <div className="flex items-baseline gap-2 text-[12.5px]">
                    <span className="w-5 shrink-0 tabular-nums text-muted">{it.rank}</span>
                    <span className="min-w-0 flex-1 truncate font-medium">
                      {it.doc_title}
                      <span className="font-normal text-muted"> {sourceLocation(it, t)}</span>
                    </span>
                    {showMovement && typeof was === "number" && moved !== 0 && (
                      <Tooltip content={t("debug.was", { n: was })}>
                        <span className={cn("inline-flex items-center text-[11px] tabular-nums", moved > 0 ? "text-celadon-deep" : "text-muted")}>
                          {moved > 0 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
                          {Math.abs(moved)}
                        </span>
                      </Tooltip>
                    )}
                    <span className="shrink-0 tabular-nums text-[11.5px] text-muted">{format(it.score)}</span>
                  </div>
                  <div className="ml-7 mt-1 flex items-center gap-2">
                    <div className="h-1 flex-1 overflow-hidden rounded-full bg-mist">
                      <div
                        className={cn("h-full rounded-full", used ? "bg-seal" : "bg-celadon")}
                        style={{ width: `${Math.max(4, (it.score / max) * 100)}%` }}
                      />
                    </div>
                  </div>
                  <p className="ml-7 mt-1 line-clamp-2 text-[12px] leading-relaxed text-muted">{it.text}</p>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}

const STAGE_ORDER = ["rewrite", "retrieve_bm25", "retrieve_vector", "retrieve_fusion", "retrieve_rerank", "generate"];

export function StageBar({ stages }: { stages: Record<string, number> }) {
  const { t } = useI18n();
  const entries = STAGE_ORDER.filter((k) => stages[k] != null && stages[k] > 0).map((k) => [k, stages[k]] as const);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (!total) return null;
  const shades = ["bg-celadon-deep", "bg-celadon", "bg-celadon/70", "bg-mist", "bg-celadon/45", "bg-seal/70"];
  return (
    <div>
      <div className="flex h-2 overflow-hidden rounded-full">
        {entries.map(([k, v], i) => (
          <Tooltip key={k} content={`${t(`stage.${k}` as MessageKey)}: ${formatMs(v)}`}>
            <div className={cn("h-full", shades[i % shades.length])} style={{ width: `${(v / total) * 100}%` }} />
          </Tooltip>
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
        {entries.map(([k, v], i) => (
          <span key={k} className="inline-flex items-center gap-1.5">
            <span className={cn("size-2 rounded-full", shades[i % shades.length])} />
            {t(`stage.${k}` as MessageKey)} <span className="tabular-nums text-ink">{formatMs(v)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** "How I found this": keyword, meaning and reranked lists side by side, with scores. */
export function RetrievalPanel({
  retrieval,
  stages,
  onOpen,
}: {
  retrieval: RetrievalDebug;
  stages: Record<string, number>;
  onOpen: (ref: SourceRef) => void;
}) {
  const { t } = useI18n();
  const usedIds = new Set(retrieval.final.map((i) => i.chunk_id));
  const keyword = mergeLists(retrieval.lists, "bm25");
  const meaning = mergeLists(retrieval.lists, "vector");
  const reranked = retrieval.reranked.length > 0;
  const last = reranked ? retrieval.reranked : retrieval.fused;

  const columns = [
    keyword.length || retrieval.mode !== "vector"
      ? { key: "kw", title: "debug.keyword" as const, hint: "debug.keyword.hint" as const, items: keyword, format: (n: number) => n.toFixed(2) }
      : null,
    meaning.length || retrieval.mode !== "bm25"
      ? { key: "mn", title: "debug.meaning" as const, hint: "debug.meaning.hint" as const, items: meaning, format: (n: number) => n.toFixed(3) }
      : null,
    retrieval.mode === "hybrid" || retrieval.mode === "hybrid_rerank"
      ? {
          key: "final",
          title: reranked ? ("debug.final" as const) : ("debug.fused" as const),
          hint: reranked ? ("debug.final.hint" as const) : ("debug.fused.hint" as const),
          items: last,
          format: (n: number) => (reranked ? n.toFixed(3) : n.toFixed(4)),
          movement: reranked,
        }
      : null,
  ].filter((c): c is NonNullable<typeof c> => c !== null);

  return (
    <div className="space-y-5 rounded-lg border border-mist bg-paper/60 p-4">
      <dl className="grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-[auto_1fr]">
        <dt className="text-muted">{t("chat.searchedAs")}</dt>
        <dd className="font-medium">{retrieval.query}</dd>
        {retrieval.extra_queries.map((q) => (
          <div key={q} className="contents">
            <dt className="text-muted">{t("chat.alsoSearched")}</dt>
            <dd className="font-medium">{q}</dd>
          </div>
        ))}
      </dl>

      <div className={cn("grid gap-5", columns.length === 3 ? "lg:grid-cols-3" : columns.length === 2 ? "md:grid-cols-2" : "")}>
        {columns.map((c) => (
          <Column
            key={c.key}
            title={c.title}
            hint={c.hint}
            items={c.items}
            usedIds={usedIds}
            format={c.format}
            showMovement={"movement" in c ? c.movement : false}
            onOpen={onOpen}
          />
        ))}
      </div>
      <p className="flex items-center gap-2 text-[12px] text-muted">
        <span className="inline-block h-1 w-5 rounded-full bg-seal" /> {t("debug.used")}
      </p>

      <div>
        <h4 className="mb-2 text-[13px] font-semibold">{t("chat.latency")}</h4>
        <StageBar stages={stages} />
      </div>
    </div>
  );
}
