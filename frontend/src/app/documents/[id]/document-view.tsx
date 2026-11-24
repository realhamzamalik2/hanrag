"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { SourceViewer } from "@/components/source-viewer";
import { api, type ChunkInfo, type DocumentInfo } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export function DocumentView({ id }: { id: string }) {
  const { t } = useI18n();
  const params = useSearchParams();
  const page = Number(params.get("page") ?? "1") || 1;
  const chunkId = params.get("chunk") ?? undefined;
  const [doc, setDoc] = useState<DocumentInfo | null>(null);
  const [chunk, setChunk] = useState<ChunkInfo | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.document(id).then(setDoc).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(() => {
    if (!chunkId) return;
    api
      .chunks(id, page)
      .then((cs) => setChunk(cs.find((c) => c.id === chunkId) ?? null))
      .catch(() => setChunk(null));
  }, [id, page, chunkId]);

  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-mist px-5 py-2.5 md:px-8">
        <Link href="/documents" className="inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink">
          <ArrowLeft className="size-3.5" /> {t("docs.title")}
        </Link>
      </div>
      {error && <p className="m-8 text-sm text-seal">{error}</p>}
      {doc && (
        <div className="mx-auto flex w-full max-w-[900px] flex-1 flex-col">
          <SourceViewer
            key={`${page}-${chunkId}-${chunk?.id ?? ""}`}
            full
            source={{
              document_id: doc.id,
              doc_title: doc.title,
              page,
              paginated: doc.paginated,
              chunk_id: chunkId,
              section: chunk?.section,
              text: chunk?.text,
            }}
          />
        </div>
      )}
    </main>
  );
}
