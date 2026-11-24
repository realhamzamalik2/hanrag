# HanRAG web app

Next.js 16 + TypeScript + Tailwind CSS 4 + shadcn/ui-style components (Radix primitives).

- **Ask**: streaming answers, numbered citations drawn as seals; a citation opens the source page with the passage highlighted (PDF via pdf.js, other formats as text). "How I found this" shows keyword, meaning and reranked results side by side.
- **Documents**: drag-and-drop upload with ingestion progress, document list with stats.
- **Evaluation**: live usage and per-stage latency from request traces; benchmark results are added in the evaluation step.
- Korean / English interface, light / dark theme.

```bash
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm install
npm run dev                  # or: npm run build && npm run start
```

On Windows, `scripts\run_app.ps1` in the repo root starts the database, the API and this app together.
