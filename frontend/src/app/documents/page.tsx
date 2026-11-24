"use client";

import { CheckCircle2, FileUp, Trash2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { api, type DocumentInfo, type Job } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { cn, formatNumber } from "@/lib/utils";

const ACCEPT = ".pdf,.docx,.txt,.md,.markdown,.hwp,.hwpx";

function JobRow({ job }: { job: Job }) {
  const { t } = useI18n();
  const label: MessageKey =
    job.status === "failed"
      ? "docs.job.failed"
      : job.status === "done"
        ? job.skipped
          ? "docs.job.skipped"
          : "docs.job.done"
        : (`docs.job.${job.stage}` as MessageKey);
  return (
    <li className="flex items-center gap-4 py-2.5">
      <span className="min-w-0 flex-1 truncate text-sm">{job.filename}</span>
      <span
        className={cn(
          "flex w-40 shrink-0 items-center gap-1.5 text-[12.5px]",
          job.status === "failed" ? "text-seal" : job.status === "done" ? "text-celadon-deep" : "text-muted",
        )}
      >
        {job.status === "done" && <CheckCircle2 className="size-3.5" />}
        {job.status === "failed" && <TriangleAlert className="size-3.5" />}
        {t(label)}
      </span>
      <Progress value={job.status === "done" ? 1 : job.progress} className="w-32 shrink-0" />
      {job.error && <span className="sr-only">{job.error}</span>}
    </li>
  );
}

export default function DocumentsPage() {
  const { t, locale } = useI18n();
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [dragging, setDragging] = useState(false);
  const [toDelete, setToDelete] = useState<DocumentInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    api
      .documents()
      .then((d) => {
        setDocs(d);
        setLoadError(null);
      })
      .catch((e: Error) => setLoadError(e.message));
  }, []);
  useEffect(load, [load]);

  // Poll running jobs once a second; refresh the list when one finishes.
  useEffect(() => {
    const active = jobs.filter((j) => j.status === "queued" || j.status === "running");
    if (active.length === 0) return;
    const timer = setInterval(async () => {
      const updated = await Promise.all(active.map((j) => api.job(j.id).catch(() => j)));
      setJobs((all) => all.map((j) => updated.find((u) => u.id === j.id) ?? j));
      updated.forEach((u) => {
        if (u.status === "failed") toast.error(`${u.filename}: ${u.error ?? t("docs.job.failed")}`);
      });
      if (updated.some((u) => u.status === "done" || u.status === "failed")) load();
    }, 1000);
    return () => clearInterval(timer);
  }, [jobs, load, t]);

  const upload = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      try {
        const job = await api.upload(file);
        setJobs((j) => [job, ...j]);
      } catch (e) {
        toast.error(`${file.name}: ${(e as Error).message}`);
      }
    }
  };

  const confirmDelete = async () => {
    if (!toDelete) return;
    try {
      await api.deleteDocument(toDelete.id);
      toast.success(t("docs.deleted", { name: toDelete.title }));
      setToDelete(null);
      load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const ready = docs?.filter((d) => d.status === "ready") ?? [];
  const totals = ready.reduce((s, d) => ({ pages: s.pages + d.num_pages, chunks: s.chunks + d.num_chunks }), { pages: 0, chunks: 0 });
  const dateFmt = new Intl.DateTimeFormat(locale, { dateStyle: "medium" });

  return (
    <main className="mx-auto w-full max-w-[1040px] px-5 py-8 md:px-10">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">{t("docs.title")}</h1>
      <p className="mt-2 max-w-[70ch] text-[15px] text-muted">{t("docs.subtitle")}</p>
      {docs && (
        <p className="mt-4 text-sm">
          <strong className="tabular-nums">{formatNumber(ready.length, locale)}</strong> {t("docs.stat.documents")}
          <span className="mx-3 text-mist">|</span>
          <strong className="tabular-nums">{formatNumber(totals.pages, locale)}</strong> {t("docs.stat.pages")}
          <span className="mx-3 text-mist">|</span>
          <strong className="tabular-nums">{formatNumber(totals.chunks, locale)}</strong> {t("docs.stat.chunks")}
        </p>
      )}

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) upload(e.dataTransfer.files);
        }}
        className={cn(
          "mt-6 flex flex-col items-center rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors",
          dragging ? "border-celadon bg-celadon-wash" : "border-mist bg-surface",
        )}
      >
        <FileUp className="size-6 text-celadon-deep" />
        <p className="mt-2 text-[15px] font-medium">{t("docs.drop")}</p>
        <p className="mt-1 text-[13px] text-muted">{t("docs.drop.hint")}</p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => inputRef.current?.click()}>
          {t("docs.choose")}
        </Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) upload(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {jobs.length > 0 && <ul className="mt-4 divide-y divide-mist border-y border-mist">{jobs.map((j) => <JobRow key={j.id} job={j} />)}</ul>}

      {loadError && (
        <p className="mt-8 rounded-md border border-seal/30 bg-seal-wash px-4 py-3 text-sm text-seal">{loadError}</p>
      )}

      {docs && docs.length === 0 && <p className="mt-10 text-center text-muted">{t("docs.empty")}</p>}

      {docs && docs.length > 0 && (
        <div className="mt-8 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-mist text-[12.5px] text-muted">
                <th className="py-2 pr-4 font-medium">{t("docs.col.title")}</th>
                <th className="px-4 py-2 font-medium">{t("docs.col.lang")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("docs.col.pages")}</th>
                <th className="px-4 py-2 text-right font-medium">{t("docs.col.chunks")}</th>
                <th className="px-4 py-2 font-medium">{t("docs.col.added")}</th>
                <th className="py-2 pl-4" />
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.id} className="border-b border-mist/70 align-top hover:bg-surface">
                  <td className="py-3 pr-4">
                    <Link href={`/documents/${d.id}`} className="font-medium hover:text-celadon-deep hover:underline">
                      {d.title}
                    </Link>
                    <div className="mt-0.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
                      <span className="uppercase">{d.file_type}</span>
                      {d.license && <span>{d.license}</span>}
                      {d.status !== "ready" && (
                        <Badge variant={d.status === "failed" ? "seal" : "outline"}>{d.status}</Badge>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={d.lang === "ko" ? "default" : "outline"}>{t(`lang.${d.lang}` as MessageKey)}</Badge>
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{d.num_pages}</td>
                  <td className="px-4 py-3 text-right tabular-nums">{d.num_chunks}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-muted">{dateFmt.format(new Date(d.created_at))}</td>
                  <td className="py-3 pl-4 text-right">
                    <Button variant="ghost" size="icon-sm" onClick={() => setToDelete(d)} aria-label={`${t("docs.delete")} ${d.title}`}>
                      <Trash2 className="text-muted" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={toDelete !== null} onOpenChange={(o) => !o && setToDelete(null)}>
        <DialogContent>
          <DialogTitle className="text-base font-semibold">{t("docs.delete")}</DialogTitle>
          <DialogDescription className="mt-2 text-sm text-muted">
            {toDelete && t("docs.delete.confirm", { name: toDelete.title })}
          </DialogDescription>
          <div className="mt-5 flex justify-end gap-2">
            <DialogClose asChild>
              <Button variant="outline">{t("source.close")}</Button>
            </DialogClose>
            <Button variant="danger" onClick={confirmDelete}>
              {t("docs.delete")}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </main>
  );
}
