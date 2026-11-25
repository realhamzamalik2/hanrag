"use client";

import { useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EvalArm, EvalSummary } from "@/lib/api";
import { useI18n, type MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const METRICS = ["recall@1", "recall@5", "recall@10", "mrr@10"] as const;
type Metric = (typeof METRICS)[number];

const pct = (v: number) => `${Math.round(v * 100)}%`;
const fmt = (m: Metric, v: number) => (m === "mrr@10" ? v.toFixed(2) : pct(v));

const AXIS = { stroke: "var(--muted)", fontSize: 12 };

function TooltipBox({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="rounded-md border border-mist bg-surface px-3 py-2 text-[12px] shadow-md">
      <p className="mb-1 font-semibold text-ink">{title}</p>
      {rows.map(([k, v]) => (
        <p key={k} className="flex justify-between gap-4 text-muted">
          <span>{k}</span>
          <span className="tabular-nums text-ink">{v}</span>
        </p>
      ))}
    </div>
  );
}

/** One bar per retrieval configuration; the full pipeline is emphasised. */
export function AblationChart({ arms }: { arms: EvalArm[] }) {
  const { t } = useI18n();
  const [metric, setMetric] = useState<Metric>("recall@5");
  const data = arms.map((a) => ({ ...a, value: a.overall[metric] }));
  const best = Math.max(...data.map((d) => d.value));

  return (
    <div>
      <div role="tablist" aria-label={t("eval.metric")} className="mb-3 flex flex-wrap gap-1">
        {METRICS.map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={metric === m}
            onClick={() => setMetric(m)}
            className={cn(
              "rounded-md px-2.5 py-1 text-[12.5px] transition-colors",
              metric === m ? "bg-celadon-wash font-medium text-celadon-deep" : "text-muted hover:text-ink",
            )}
          >
            {m === "mrr@10" ? "MRR@10" : `Recall@${m.split("@")[1]}`}
          </button>
        ))}
      </div>
      <div className="h-[300px] w-full">
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }} barCategoryGap={8}>
            <CartesianGrid horizontal={false} stroke="var(--mist)" strokeDasharray="2 4" />
            <XAxis
              type="number"
              domain={[0, 1]}
              tickFormatter={(v: number) => fmt(metric, v)}
              tick={AXIS}
              axisLine={false}
              tickLine={false}
            />
            <YAxis type="category" dataKey="label" width={170} tick={{ ...AXIS, fill: "var(--ink)" }} axisLine={false} tickLine={false} />
            <Tooltip
              cursor={{ fill: "var(--celadon-wash)", opacity: 0.6 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const a = payload[0].payload as EvalArm;
                return (
                  <TooltipBox
                    title={a.label}
                    rows={[
                      ["Recall@1", pct(a.overall["recall@1"])],
                      ["Recall@5", pct(a.overall["recall@5"])],
                      ["Recall@10", pct(a.overall["recall@10"])],
                      ["MRR@10", a.overall["mrr@10"].toFixed(3)],
                      [t("eval.medianLatency"), `${(a.latency_ms.p50 / 1000).toFixed(1)} s`],
                    ]}
                  />
                );
              }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} maxBarSize={22}>
              {data.map((d) => (
                <Cell key={d.id} fill={d.id === "hybrid_rerank" ? "var(--celadon-deep)" : "var(--celadon)"} fillOpacity={d.id === "hybrid_rerank" ? 1 : 0.55} />
              ))}
              <LabelList
                dataKey="value"
                position="right"
                formatter={(v: unknown) => fmt(metric, Number(v))}
                fill="var(--ink)"
                fontSize={12}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[12px] text-muted">
        {t("eval.bestValue", { v: fmt(metric, best) })}
      </p>
    </div>
  );
}

/** Direct label at the end of a line (identity is never colour alone). */
function endLabel(p: { index?: number; x?: number | string; y?: number | string }, n: number, text: string) {
  if (p.index !== n - 1) return null;
  return (
    <text x={Number(p.x ?? 0) + 10} y={Number(p.y ?? 0) + 4} fill="var(--ink)" fontSize={11.5}>
      {text}
    </text>
  );
}

/** Early-refusal threshold: share of unanswerable questions refused vs answerable ones lost. */
export function GateChart({ gate }: { gate: NonNullable<EvalSummary["retrieval"]>["refusal_gate"] }) {
  const { t } = useI18n();
  const data = gate.sweep.map((r) => ({ ...r, label: String(r.threshold) }));
  const last = data[data.length - 1];
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 110, bottom: 4, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--mist)" strokeDasharray="2 4" />
          <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
          <YAxis domain={[0, 1]} tickFormatter={pct} tick={AXIS} axisLine={false} tickLine={false} width={44} />
          <Tooltip
            cursor={{ stroke: "var(--muted)", strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const r = payload[0].payload as (typeof data)[number];
              return (
                <TooltipBox
                  title={`${t("eval.threshold")} ${r.threshold}`}
                  rows={[
                    [t("eval.gate.unanswerable"), pct(r.unanswerable_refused)],
                    [t("eval.gate.answerable"), pct(r.answerable_refused)],
                  ]}
                />
              );
            }}
          />
          <Legend verticalAlign="top" height={28} iconType="plainline" wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} />
          <Line
            name={t("eval.gate.unanswerable")}
            dataKey="unanswerable_refused"
            stroke="var(--chart-a)"
            strokeWidth={2}
            dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)" }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          >
            <LabelList dataKey="unanswerable_refused" content={(p) => endLabel(p, data.length, pct(last.unanswerable_refused))} />
          </Line>
          <Line
            name={t("eval.gate.answerable")}
            dataKey="answerable_refused"
            stroke="var(--chart-b)"
            strokeWidth={2}
            strokeDasharray="6 4"
            dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)" }}
            activeDot={{ r: 5 }}
            isAnimationActive={false}
          >
            <LabelList dataKey="answerable_refused" content={(p) => endLabel(p, data.length, pct(last.answerable_refused))} />
          </Line>
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ArmTable({ arms }: { arms: EvalArm[] }) {
  const { t } = useI18n();
  const groups: [string, MessageKey][] = [
    ["ko", "eval.group.ko"],
    ["en", "eval.group.en"],
    ["cross", "eval.group.cross"],
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <caption className="sr-only">{t("eval.ablation")}</caption>
        <thead>
          <tr className="border-b border-mist text-[12px] text-muted">
            <th className="py-2 pr-3 font-medium">{t("eval.col.config")}</th>
            <th className="px-3 py-2 text-right font-medium">R@1</th>
            <th className="px-3 py-2 text-right font-medium">R@5</th>
            <th className="px-3 py-2 text-right font-medium">R@10</th>
            <th className="px-3 py-2 text-right font-medium">MRR</th>
            {groups.map(([g, k]) => (
              <th key={g} className="px-3 py-2 text-right font-medium">
                {t(k)} R@5
              </th>
            ))}
            <th className="py-2 pl-3 text-right font-medium">{t("eval.medianLatency")}</th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => (
            <tr key={a.id} className={cn("border-b border-mist/70", a.id === "hybrid_rerank" && "font-semibold")}>
              <td className="py-2 pr-3">{a.label}</td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(a.overall["recall@1"])}</td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(a.overall["recall@5"])}</td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(a.overall["recall@10"])}</td>
              <td className="px-3 py-2 text-right tabular-nums">{a.overall["mrr@10"].toFixed(3)}</td>
              {groups.map(([g]) => (
                <td key={g} className="px-3 py-2 text-right tabular-nums">
                  {a.by_type[g] ? pct(a.by_type[g]["recall@5"]) : "–"}
                </td>
              ))}
              <td className="py-2 pl-3 text-right tabular-nums">{(a.latency_ms.p50 / 1000).toFixed(1)} s</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
