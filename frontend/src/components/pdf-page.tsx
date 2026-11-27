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
      // Find the passage by its opening and closing words. Slide a window along the passage,
      // because its first words may not sit next to the rest on the page (a title above a
      // printed source line, for example), and extraction can differ slightly at the edges.
      const W = 16;
      let start = -1;
      for (let k = 0; k + W <= target.length && start === -1; k += 8) {
        start = page.indexOf(target.slice(k, k + W));
      }
      if (start === -1) start = page.indexOf(target);
      if (start === -1) return setMarked(new Set());
      let end = -1;
      for (let k = target.length; k - W >= 0 && end === -1; k -= 8) {
        const j = page.indexOf(target.slice(k - W, k), start);
        if (j !== -1) end = j + W;
      }
      if (end === -1) end = Math.min(page.length, start + target.length);
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
