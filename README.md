# HanRAG

**Korean + English Retrieval-Augmented Generation with exact citations.**

Upload Korean and English documents (PDF, DOCX, TXT, Markdown, HWP/HWPX), ask questions in either language, and get answers with numbered citations (document + page + passage). HanRAG says "I don't know" when the documents don't support an answer, and shows exactly how retrieval worked.

> Status: **Step 2 of 5**. Ingestion, hybrid search (Kiwi BM25 + bge-m3 + RRF), cross-encoder reranking, refusal, query rewriting and a streaming FastAPI backend are done. The Next.js UI and the evaluation study are in progress.

## Why Korean needs special handling

| Problem | What HanRAG does |
|---|---|
| Korean is agglutinative: `한글을`, `한글은`, `한글이` are one word with different particles, so whitespace tokens rarely match | Kiwi morphological analysis keeps content morphemes (`한글`, `창제`) and drops particles and endings |
| PDF extraction often loses Korean word spacing | Detects abnormal spacing and restores it with Kiwi |
| Some PDFs and HWP files produce decomposed jamo (NFD) | Unicode NFC normalization before indexing |
| "N words per chunk" means very different amounts of text in Korean vs English | Chunks are sized in characters and split on Kiwi sentence boundaries |
| Users ask in English about Korean documents | bge-m3 multilingual embeddings share one vector space across languages |

## Architecture

```
INGEST   file ─► parser (PyMuPDF / python-docx / text / HWP) ─► NFC + spacing repair (Kiwi)
              ─► sentence chunker (page + section metadata) ─► bge-m3 (ONNX, CPU) ─► pgvector

QUERY    question + history
           ─► rewrite (1 LLM call): standalone follow-up + ko↔en translation
           ─► BM25 (Kiwi morphemes)  ┐
           ─► bge-m3 vectors         ┴► Reciprocal Rank Fusion ─► bge-reranker-v2-m3 (top 20)
           ─► gate: refuse early if the best passage is irrelevant (no LLM call)
           ─► Gemini (streamed) with strict [n] citations or a refusal token
           ─► citations validated against passages ─► trace saved (latency per stage)
```

### Why these choices

| Choice | Reason |
|---|---|
| **Hybrid search** | Vectors capture meaning and work across languages; BM25 nails exact terms (names, years, rare words). Each covers the other's blind spot. |
| **Kiwi tokenizer for BM25** | `훈민정음은` and `훈민정음을` both become `훈민정음`, so Korean queries match. Whitespace BM25 misses these. |
| **RRF fusion** | BM25 and cosine scores live on different scales. RRF only uses ranks (`1/(60+rank)`), so no fragile score normalization. |
| **Cross-encoder reranker** | Reads query and passage together, fixing ordering mistakes from both retrievers. Its 0 to 1 score also drives early refusal. |
| **Query translation** | BM25 cannot match an English query to Korean text. Searching with both the question and its translation fixes that. |
| **Refusal gate + refusal token** | Clearly unanswerable questions are refused before calling the LLM (saves quota); borderline ones are refused by the model itself. |

## Tech stack

Python 3.11, FastAPI, PostgreSQL 16 + pgvector, SQLAlchemy 2, Kiwi (kiwipiepy), BAAI/bge-m3, BAAI/bge-reranker-v2-m3 (int8 ONNX via fastembed), Gemini API, Next.js + TypeScript + Tailwind + shadcn/ui.

Everything runs on CPU and fits on an 8 GB RAM laptop.

## Run it locally (Windows)

Requirements: Git, [uv](https://docs.astral.sh/uv/), WSL with Ubuntu 24.04, a free Gemini API key from [Google AI Studio](https://aistudio.google.com).

```powershell
git clone https://github.com/realhamzamalik2/hanrag.git
cd hanrag
Copy-Item .env.example .env        # then add GEMINI_API_KEY and GEMINI_MODEL
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1   # deps, Postgres, models, samples

# Afterwards
powershell -ExecutionPolicy Bypass -File scripts\run_api.ps1         # API on :8000, docs at /docs
cd backend
uv run python -m scripts.ask_cli "한글은 누가 만들었나요?" --debug
uv run python -m scripts.ask_cli "Who created Hangul?"                 # cross-lingual
uv run python -m scripts.ask_cli "훈민정음 반포" --mode bm25 --tokenizer whitespace --no-llm
```

## API

Interactive docs at `http://localhost:8000/docs` (OpenAPI).

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/documents` | Upload a file; returns a job, ingestion runs in the background |
| `GET` | `/api/jobs/{id}` | Ingestion progress (`parsing`, `chunking`, `embedding`, `done`) |
| `GET` | `/api/documents` | Indexed documents with stats |
| `GET` | `/api/documents/{id}/file` | Original file (PDF viewer) |
| `GET` | `/api/documents/{id}/chunks?page=` | Chunks of a page (passage highlighting) |
| `DELETE` | `/api/documents/{id}` | Remove a document and its chunks |
| `POST` | `/api/search` | Retrieval only: BM25, vector, fused and reranked lists with scores |
| `POST` | `/api/chat` | Answer with citations (JSON) |
| `POST` | `/api/chat/stream` | Same, as Server-Sent Events: `rewrite`, `retrieval`, `token`, `done` |
| `GET` | `/api/traces`, `/api/traces/{id}` | Per-question latency per stage, tokens, retrieved passages |
| `GET` | `/api/stats`, `/api/health`, `/api/config` | Dashboard numbers and status |

Chat, search and upload are rate limited (`RATE_LIMIT`, default 20/minute per IP).

## Tests

```powershell
cd backend
uv run pytest -m "not db"     # unit tests: Korean tokenization, chunking, parsers, BM25, RRF, citations
uv run pytest -m db           # pipeline + API tests on a separate hanrag_test database
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
