"use client";

import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { TextContent, TextItem } from "pdfjs-dist/types/src/display/api";
import { Document, Page, pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = "/pdfjs/pdf.worker.min.mjs";

const PDF_OPTIONS = {
  cMapUrl: "/pdfjs/cmaps/",
  cMapPacked: true,
  standardFontDataUrl: "/pdfjs/standard_fonts/",
};

const squash = (s: string) => s.replace(/\s+/g, "");
const escapeHtml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/**
 * One PDF page, with every text line that belongs to the cited passage highlighted.
 * Matching ignores whitespace, because PDF text items and our chunk text are split
 * and spaced differently (especially in Korean).
 */
export default function PdfPage({
  url,
  page,
  highlight,
  onNumPages,
  loadingLabel,
}: {
  url: string;
  page: number;
  highlight?: string;
  onNumPages?: (n: number) => void;
  loadingLabel: string;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const target = useMemo(() => (highlight ? squash(highlight) : ""), [highlight]);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => setWidth(Math.max(280, Math.floor(entry.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Indices of the text items that make up the cited passage on this page.
  const [marked, setMarked] = useState<Set<number>>(new Set());

  const locatePassage = useCallback(
    (content: TextContent) => {
      if (!target) return setMarked(new Set());
      // Concatenate the page's text (whitespace removed) and remember where each item sits.
      const spans: [number, number][] = [];
      let page = "";
      for (const item of content.items) {
        const s = "str" in item ? squash((item as TextItem).str) : "";
        spans.push([page.length, page.length + s.length]);
        page += s;
      }
      // Find the passage by its opening and closing words (robust to small extraction diffs).
      const findPrefix = (text: string, from = 0) => {
        for (const n of [40, 24, 12]) {
          if (text.length < n) continue;
          const i = page.indexOf(text.slice(0, n), from);
          if (i !== -1) return i;
        }
        return page.indexOf(text, from);
      };
      const start = findPrefix(target);
      if (start === -1) return setMarked(new Set());
      let end = start + target.length;
      for (const n of [40, 24, 12]) {
        if (target.length < n) continue;
        const j = page.indexOf(target.slice(-n), start);
        if (j !== -1) {
          end = j + n;
          break;
        }
      }
      const hit = new Set<number>();
      spans.forEach(([a, b], i) => {
        if (b > a && a < end && b > start) hit.add(i);
      });
      setMarked(hit);
    },
    [target],
  );

  const renderText = useCallback(
    ({ str, itemIndex }: { str: string; itemIndex: number }) =>
      marked.has(itemIndex) ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str),
    [marked],
  );

  const scrollToHighlight = useCallback(() => {
    const mark = wrapRef.current?.querySelector(".react-pdf__Page__textContent mark");
    mark?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, []);

  return (
    <div ref={wrapRef} className="w-full">
      <Document
        file={url}
        options={PDF_OPTIONS}
        onLoadSuccess={(pdf) => onNumPages?.(pdf.numPages)}
        loading={<div className="py-20 text-center text-sm text-muted">{loadingLabel}</div>}
      >
        <Page
          pageNumber={page}
          width={width}
          customTextRenderer={renderText}
          onGetTextSuccess={locatePassage}
          onRenderTextLayerSuccess={scrollToHighlight}
          renderAnnotationLayer={false}
          className="overflow-hidden rounded-md border border-mist shadow-sm"
        />
      </Document>
    </div>
  );
}
