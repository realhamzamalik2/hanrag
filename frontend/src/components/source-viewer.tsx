"use client";

import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, type ChunkInfo, type DocumentInfo } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const PdfPage = dynamic(() => import("@/components/pdf-page"), { ssr: false });

/** What the viewer needs to show a cited passage. */
export interface SourceRef {
  document_id: string;
  doc_title: string;
  page: number;
  paginated: boolean;
  section?: string;
  chunk_id?: string;
  text?: string;
}

export function sourceLocation(
  ref: Pick<SourceRef, "paginated" | "page" | "section"> & { doc_title?: string },
  t: ReturnType<typeof useI18n>["t"],
) {
  if (ref.paginated) return t("source.page", { n: ref.page });
  // Markdown files often start with the title as a heading; showing it twice adds nothing.
  const section = ref.section && ref.section !== ref.doc_title ? ref.section : "";
  return section || t("source.part", { n: ref.page });
}

/** Paginated (PDF): the page with the passage highlighted. Otherwise: all passages, cited one marked. */
export function SourceViewer({ source, full = false }: { source: SourceRef; full?: boolean }) {
  const { t } = useI18n();
  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [page, setPage] = useState(source.page);
  const [numPages, setNumPages] = useState<number | null>(null);

  useEffect(() => {
    api.document(source.document_id).then(setDoc).catch(() => setDoc(null));
  }, [source.document_id]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-mist px-5 pb-3 pt-4 pr-12">
        <h2 className="font-serif text-lg font-semibold leading-snug">{source.doc_title}</h2>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
          <span>{sourceLocation({ ...source, page }, t)}</span>
          {doc?.source_url && (
            <a href={doc.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-ink">
              {doc.license ?? t("source.license")} <ExternalLink className="size-3" />
            </a>
          )}
          {!full && (
            <Link
              href={`/documents/${source.document_id}?page=${page}${source.chunk_id ? `&chunk=${source.chunk_id}` : ""}`}
              className="text-celadon-deep hover:underline"
            >
              {t("source.openFull")}
            </Link>
          )}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto bg-paper px-5 py-5">
        {source.paginated ? (
          <>
            <PdfPage
              url={api.fileUrl(source.document_id)}
              page={page}
              highlight={page === source.page ? source.text : undefined}
              onNumPages={setNumPages}
              loadingLabel={t("source.loading")}
            />
            {numPages && numPages > 1 && (
              <div className="mt-4 flex items-center justify-center gap-3 text-sm">
                <Button variant="outline" size="icon-sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} aria-label="Previous page">
                  <ChevronLeft />
                </Button>
                <span className="tabular-nums text-muted">
                  {page} / {numPages}
                </span>
                <Button variant="outline" size="icon-sm" onClick={() => setPage((p) => Math.min(numPages, p + 1))} disabled={page >= numPages} aria-label="Next page">
                  <ChevronRight />
                </Button>
              </div>
            )}
          </>
        ) : (
          <ChunkReader documentId={source.document_id} chunkId={source.chunk_id} />
        )}
      </div>
    </div>
  );
}

function ChunkReader({ documentId, chunkId }: { documentId: string; chunkId?: string }) {
  const { t } = useI18n();
  const [chunks, setChunks] = useState<ChunkInfo[] | null>(null);
  const activeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.chunks(documentId).then(setChunks).catch(() => setChunks([]));
  }, [documentId]);
  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "center" });
  }, [chunks, chunkId]);

  if (!chunks) return <p className="py-20 text-center text-sm text-muted">{t("source.loading")}</p>;

  // Precompute headings and de-duplicated bodies (neighbouring passages overlap by a sentence).
  const rows: { c: ChunkInfo; heading: string | null; body: string; active: boolean }[] = [];
  let lastSection = "";
  chunks.forEach((c, i) => {
    const active = c.id === chunkId;
    const prev = chunks[i - 1];
    const overlap = prev && prev.page === c.page ? prev.char_end - c.char_start : 0;
    const body = !active && overlap > 0 ? c.text.slice(overlap).trimStart() : c.text;
    const heading = c.section && c.section !== lastSection ? c.section : null;
    if (c.section) lastSection = c.section;
    if (body) rows.push({ c, heading, body, active });
  });

  return (
    <article className="prose-reading mx-auto">
      {rows.map(({ c, heading, body, active }) => (
        <div key={c.id}>
          {heading && <h3 className="mb-2 mt-6 font-sans text-[15px] font-semibold text-ink">{heading}</h3>}
          <div
            ref={active ? activeRef : undefined}
            className={cn("mb-3 rounded-sm", active && "-mx-3 border-l-[3px] border-seal bg-seal-wash px-3 py-2")}
            aria-label={active ? t("source.cited") : undefined}
          >
            {body}
          </div>
        </div>
      ))}
    </article>
  );
}
