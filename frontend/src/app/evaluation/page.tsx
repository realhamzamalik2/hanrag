"use client";

import { useEffect, useState } from "react";

import { StageBar } from "@/components/chat/retrieval-panel";
import { Badge } from "@/components/ui/badge";
import { api, type Stats, type TraceSummary } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { formatMs, formatNumber } from "@/lib/utils";

export default function EvaluationPage() {
  const { t, locale } = useI18n();
  const [stats, setStats] = useState<Stats | null>(null);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.stats(), api.traces(30)])
      .then(([s, tr]) => {
        setStats(s);
        setTraces(tr);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const timeFmt = new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "short" });

  return (
    <main className="mx-auto w-full max-w-[1040px] px-5 py-8 md:px-10">
      <h1 className="font-serif text-3xl font-semibold tracking-tight">{t("eval.title")}</h1>
      <p className="mt-2 max-w-[70ch] text-[15px] text-muted">{t("eval.subtitle")}</p>

      <section className="mt-8 border-l-2 border-celadon pl-5">
        <h2 className="text-[17px] font-semibold">{t("eval.pending.title")}</h2>
        <p className="mt-1 max-w-[70ch] text-[14.5px] text-muted">{t("eval.pending.body")}</p>
      </section>

      {error && <p className="mt-8 rounded-md border border-seal/30 bg-seal-wash px-4 py-3 text-sm text-seal">{error}</p>}

      {stats && (
        <section className="mt-10">
          <h2 className="text-[17px] font-semibold">{t("eval.live")}</h2>
          <dl className="mt-4 grid gap-6 sm:grid-cols-3">
            {(
              [
                ["eval.questions", formatNumber(stats.questions, locale)],
                ["eval.refusals", formatNumber(stats.refusals, locale)],
                ["eval.latency", formatMs(stats.avg_latency_ms)],
              ] as [MessageKey, string][]
            ).map(([k, v]) => (
              <div key={k}>
                <dt className="text-[13px] text-muted">{t(k)}</dt>
                <dd className="mt-1 font-serif text-3xl font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
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
                    <td className="whitespace-nowrap px-4 py-3 text-muted">
                      {t(`chat.mode.${tr.mode}` as MessageKey)}
                    </td>
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
