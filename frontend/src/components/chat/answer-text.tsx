"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Seal } from "@/components/seal";

/**
 * Renders the model's answer as Markdown and turns every [n] into a clickable seal.
 * [n] becomes a link to "#cite-n" before parsing, and the link renderer swaps it for a Seal.
 */
export function AnswerText({
  text,
  streaming,
  activeCitation,
  onCite,
  citeLabel,
}: {
  text: string;
  streaming?: boolean;
  activeCitation?: number | null;
  onCite: (n: number) => void;
  citeLabel: (n: number) => string;
}) {
  const md = text.replace(/\[(\d{1,2})\]/g, "[$1](#cite-$1)");
  return (
    <div className={streaming ? "prose-reading caret" : "prose-reading"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            const m = href?.match(/^#cite-(\d+)$/);
            if (m) {
              const n = Number(m[1]);
              return <Seal n={n} active={activeCitation === n} onClick={() => onCite(n)} label={citeLabel(n)} />;
            }
            return (
              <a href={href} target="_blank" rel="noreferrer" className="text-celadon-deep underline">
                {children}
              </a>
            );
          },
        }}
      >
        {md}
      </ReactMarkdown>
    </div>
  );
}
