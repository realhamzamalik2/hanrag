// Copies the pdf.js worker, CJK character maps and standard fonts into public/pdfjs.
// Korean PDFs need the cMaps to render text correctly.
import { cpSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const pdfjsRoot = dirname(require.resolve("pdfjs-dist/package.json", {
  paths: [dirname(require.resolve("react-pdf/package.json"))],
}));
const out = join(process.cwd(), "public", "pdfjs");
mkdirSync(out, { recursive: true });
cpSync(join(pdfjsRoot, "build", "pdf.worker.min.mjs"), join(out, "pdf.worker.min.mjs"));
for (const dir of ["cmaps", "standard_fonts"]) {
  if (existsSync(join(pdfjsRoot, dir))) cpSync(join(pdfjsRoot, dir), join(out, dir), { recursive: true });
}
console.log("pdf.js assets copied to public/pdfjs");
