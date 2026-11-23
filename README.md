# HanRAG

**Korean + English Retrieval-Augmented Generation with exact citations.**

Upload Korean and English documents (PDF, DOCX, TXT, Markdown, HWP/HWPX), ask questions in either language, and get answers with numbered citations (document + page + passage). HanRAG says "I don't know" when the documents don't support an answer, and shows exactly how retrieval worked.

> Status: **Step 1 of 5** (ingestion, Korean-aware chunking, vector search, cited answers via CLI). Hybrid search, reranking, the API, the Next.js UI and the evaluation study are in progress.

## Why Korean needs special handling

| Problem | What HanRAG does |
|---|---|
| Korean is agglutinative: `한글을`, `한글은`, `한글이` are one word with different particles, so whitespace tokens rarely match | Kiwi morphological analysis keeps content morphemes (`한글`, `창제`) and drops particles and endings |
| PDF extraction often loses Korean word spacing | Detects abnormal spacing and restores it with Kiwi |
| Some PDFs and HWP files produce decomposed jamo (NFD) | Unicode NFC normalization before indexing |
| "N words per chunk" means very different amounts of text in Korean vs English | Chunks are sized in characters and split on Kiwi sentence boundaries |
| Users ask in English about Korean documents | bge-m3 multilingual embeddings share one vector space across languages |

## Architecture (Step 1)

```
file ─► parser (PyMuPDF / python-docx / text / HWP) ─► normalize + spacing fix (Kiwi)
     ─► sentence chunker (page + section metadata) ─► bge-m3 embeddings (ONNX, CPU)
     ─► PostgreSQL + pgvector (HNSW, cosine)

question ─► bge-m3 ─► pgvector top-k ─► score gate (refuse early) ─► Gemini (free tier)
         ─► [n] citations validated against retrieved passages ─► trace saved to Postgres
```

## Tech stack

Python 3.11, FastAPI, PostgreSQL 16 + pgvector, SQLAlchemy 2, Kiwi (kiwipiepy), BAAI/bge-m3, BAAI/bge-reranker-v2-m3 (int8 ONNX via fastembed), Gemini API, Next.js + TypeScript + Tailwind + shadcn/ui.

Everything runs on CPU and fits on an 8 GB RAM laptop.

## Run it locally (Windows)

Requirements: Git, [uv](https://docs.astral.sh/uv/), WSL with Ubuntu 24.04, a free Gemini API key from [Google AI Studio](https://aistudio.google.com).

```powershell
git clone https://github.com/realhamzamalik2/hanrag.git
cd hanrag
Copy-Item .env.example .env        # then add GEMINI_API_KEY and GEMINI_MODEL

# PostgreSQL + pgvector inside WSL
wsl bash scripts/setup_postgres_wsl.sh

cd backend
uv sync
uv run python -m scripts.healthcheck          # checks Kiwi, DB, embedding model
uv run python -m scripts.fetch_samples        # downloads CC BY-SA Wikipedia samples
uv run python -m scripts.ingest_cli ../data/samples
uv run python -m scripts.ask_cli "한글은 누가 만들었나요?"
uv run python -m scripts.ask_cli "Who created Hangul?"   # cross-lingual
```

## Tests

```powershell
cd backend
uv run pytest -m "not db"     # unit tests: Korean tokenization, chunking, parsers, citations
uv run pytest -m db           # integration test against PostgreSQL + pgvector
```

## Models and licenses

| Component | License |
|---|---|
| [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | MIT |
| [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | Apache-2.0 |
| [Kiwi / kiwipiepy](https://github.com/bab2min/kiwipiepy) | LGPL-3.0 |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 |
| Sample documents (Wikipedia) | CC BY-SA 4.0, see `data/samples/SOURCES.md` |

HanRAG is licensed under AGPL-3.0 (required by PyMuPDF).
