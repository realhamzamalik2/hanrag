# HanRAG

**Korean + English Retrieval-Augmented Generation with exact citations.**

Upload Korean and English documents (PDF, DOCX, TXT, Markdown, HWP/HWPX), ask questions in either language, and get answers with numbered citations (document + page + passage). HanRAG says "I don't know" when the documents don't support an answer, and shows exactly how retrieval worked.

> Status: backend, Next.js UI (documents, chat with clickable citations, retrieval debug panel), a 50-question evaluation and Docker Compose are done. A demo GIF comes next.

**Results on a 50-question Korean/English set:** retrieval Recall@5 95% (whitespace BM25: 65%), answers correct 95%, every answer cites the evidence passage, 9 of 10 unanswerable questions refused. [Details below](#evaluation).

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
           ─► bge-m3 vectors         ┴► Reciprocal Rank Fusion ─► bge-reranker-v2-m3 (top 12,
                                                             each passage scored with the
                                                             query in its own language)
           ─► gate: refuse early if the best passage is irrelevant (no LLM call)
           ─► Gemini (streamed), answer language fixed in code, strict [n] citations or refusal
           ─► citations validated against passages ─► trace saved (latency per stage)
```

### Why these choices

| Choice | Reason |
|---|---|
| **Hybrid search** | Vectors capture meaning and work across languages; BM25 nails exact terms (names, years, rare words). Each covers the other's blind spot. |
| **Kiwi tokenizer for BM25** | `훈민정음은` and `훈민정음을` both become `훈민정음`, so Korean queries match. Whitespace BM25 misses these. |
| **RRF fusion** | BM25 and cosine scores live on different scales. RRF only uses ranks (`1/(60+rank)`), so no fragile score normalization. |
| **int8 bge-m3** | The fp32 model needs about 2.3 GB of RAM and crashed next to the reranker on an 8 GB laptop. Dynamic int8 quantization cuts it to about 570 MB; the eval measures the quality cost. |
| **Cross-encoder reranker** | Reads query and passage together, fixing ordering mistakes from both retrievers. Its 0 to 1 score also drives early refusal. |
| **Query translation** | BM25 cannot match an English query to Korean text. Searching with both the question and its translation fixes that. |
| **Language-matched reranking** | The cross-encoder scored an English question against Korean passages near 0, so the refusal gate rejected answerable questions. Each passage is now scored with the query variant in its own language: same number of pairs, no extra time. |
| **Refusal gate + refusal token** | Clearly unanswerable questions are refused before calling the LLM (saves quota); borderline ones are refused by the model itself. |

## Tech stack

Python 3.11, FastAPI, PostgreSQL 16 + pgvector, SQLAlchemy 2, Kiwi (kiwipiepy), BAAI/bge-m3 (int8 ONNX), BAAI/bge-reranker-v2-m3 (int8 ONNX, run directly with onnxruntime), Gemini API, Next.js + TypeScript + Tailwind + shadcn/ui.

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

## Run it with Docker

Needs Docker and about 4 GB of free RAM. Everything stays on CPU.

```bash
cp .env.example .env              # add GEMINI_API_KEY and GEMINI_MODEL
docker compose up --build         # Postgres + pgvector, API on :8000, web app on :3000
# optional: download and index the 9 openly licensed sample documents
docker compose exec api python -m scripts.fetch_samples
docker compose exec api python -m scripts.ingest_cli /app/data/samples
```

Open http://localhost:3000. The first start downloads the two models (about 1.2 GB) into a Docker volume. CI builds both images, starts the stack and checks the API, the web proxy and the Evaluation page on every push.

## Evaluation

50 questions written from the sample documents: 18 Korean, 12 English, 10 cross-lingual (English question on a Korean document or the reverse) and 10 unanswerable traps. A passage counts as relevant when it contains the question's evidence sentence; every evidence string was checked by code against the indexed text. Data: [`eval/dataset/qa.jsonl`](eval/dataset/qa.jsonl). Full numbers: [`eval/results/RESULTS.md`](eval/results/RESULTS.md).

### Retrieval ablation

Top 10 passages for the 40 answerable questions, no query translation, no LLM.

| Configuration | Recall@1 | Recall@5 | MRR@10 | Korean R@5 | Cross-lingual R@5 | Median time |
|---|---|---|---|---|---|---|
| BM25, whitespace tokens | 45% | 65% | 0.533 | 61% | 30% | 0.0 s |
| BM25, Kiwi morphemes | 52% | 78% | 0.614 | 89% | 30% | 0.0 s |
| Vector (bge-m3 int8) | 50% | 95% | 0.705 | 94% | 90% | 0.1 s |
| Hybrid RRF, Kiwi | 60% | 85% | 0.713 | 100% | 40% | 0.1 s |
| **Hybrid RRF + reranker** | **78%** | **95%** | **0.841** | **100%** | 80% | 14.0 s |

What it shows:
- **Kiwi matters for Korean.** Korean Recall@5 for keyword search goes from 61% to 89% just by indexing morphemes instead of space-separated words.
- **The reranker fixes ordering.** Recall@1 rises from 60% to 78% and MRR from 0.71 to 0.84. On a CPU laptop it costs about 11 s per question, the largest part of the latency.
- **Translation closes the cross-lingual gap.** Keyword search cannot match English to Korean (30%). With the query translated as well, end-to-end retrieval reaches 100% Recall@5 on cross-lingual questions.

### Answers, and what error analysis fixed

The default pipeline (hybrid + reranker, query rewrite, Gemini `gemini-3.5-flash-lite`) answered all 50 questions. Reading the wrong answers of the first run found three problems:

1. **Wrong language.** 7 English questions were answered correctly but in Korean, because most passages were Korean. The answer language is now detected in code and stated in the prompt.
2. **Cross-lingual refusals.** The reranker scored an English question against Korean passages at 0.002 to 0.03, below the refusal gate. Each passage is now scored with the query in its own language.
3. **Over-citation.** Answers cited extra passages on the same topic. The prompt now allows only passages that directly state the fact.

| Metric | First run | After fixes |
|---|---|---|
| Answers with all required facts | 80% | **95%** |
| Answers in the question's language | 76% | **100%** |
| A cited passage contains the evidence | 97% | **100%** |
| Answers supported by their citations (LLM judge) | 100% | 100% |
| Answerable questions wrongly refused | 8% | **5%** |
| Unanswerable questions refused | 100% | 90% |
| Median time per question | 17.0 s | 15.1 s |

Honest caveats:
- **One hallucination.** "What was King Sejong's favorite food?" is a trap: the document only says he ate meat and took white rooster as a prescribed diet for diabetes. The model presented that as his "favorite food" with an invented detail. The question stays in the set.
- **The two remaining false refusals** happened when the free Gemini tier returned 503 during query rewriting, so no translation was produced. The rewrite now retries once.
- **The judge is the same model that answers**, so the faithfulness number is an indicator, not ground truth. An earlier judge bug (passages renumbered, so `[3]` pointed nowhere) made it report 73%; both runs were re-judged after the fix.
- 50 questions over 9 documents is a small set: treat differences of one or two questions as noise.

Run it yourself (about 40 minutes on an 8 GB laptop, about 140 free-tier Gemini calls, resumable):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_eval.ps1              # everything
powershell -ExecutionPolicy Bypass -File scripts\run_eval.ps1 -RetrievalOnly   # no Gemini calls
```

The Evaluation page in the web app shows the same results as charts, plus live numbers from real questions.

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
| `GET` | `/api/eval` | Saved evaluation results (`eval/results/summary.json`) |

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
| [gpahal/bge-m3-onnx-int8](https://huggingface.co/gpahal/bge-m3-onnx-int8) (int8 export of bge-m3) | MIT |
| [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | Apache-2.0 |
| [Kiwi / kiwipiepy](https://github.com/bab2min/kiwipiepy) | LGPL-3.0 |
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 |
| Sample documents (Wikipedia) | CC BY-SA 4.0, see `data/samples/SOURCES.md` |

HanRAG is licensed under AGPL-3.0 (required by PyMuPDF).
