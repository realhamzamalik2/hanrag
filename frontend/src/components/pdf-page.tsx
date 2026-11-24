"use client";

import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

  const renderText = useCallback(
    ({ str }: { str: string }) => {
      const s = squash(str);
      if (target && s.length >= 3 && target.includes(s)) return `<mark>${escapeHtml(str)}</mark>`;
      return escapeHtml(str);
    },
    [target],
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
          onRenderTextLayerSuccess={scrollToHighlight}
          renderAnnotationLayer={false}
          className="overflow-hidden rounded-md border border-mist shadow-sm"
        />
      </Document>
    </div>
  );
}
