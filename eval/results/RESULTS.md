# HanRAG evaluation results

Generated 2026-11-26 12:07 UTC on 50 questions ({'ko': 18, 'en': 12, 'cross_en_ko': 6, 'cross_ko_en': 4, 'unanswerable': 10}).

## Retrieval ablation (top 10 passages, no query translation)

| Configuration | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@10 | Korean R@5 | English R@5 | Cross-lingual R@5 | Median latency |
|---|---|---|---|---|---|---|---|---|---|
| BM25, whitespace tokens | 45% | 60% | 65% | 68% | 0.533 | 61% | 100% | 30% | 0.0 s |
| BM25, Kiwi morphemes | 52% | 62% | 78% | 82% | 0.614 | 89% | 100% | 30% | 0.0 s |
| Vector (bge-m3 int8) | 50% | 90% | 95% | 100% | 0.705 | 94% | 100% | 90% | 0.1 s |
| Hybrid RRF, whitespace | 50% | 72% | 82% | 92% | 0.624 | 89% | 100% | 50% | 0.1 s |
| Hybrid RRF, Kiwi | 60% | 82% | 85% | 90% | 0.713 | 100% | 100% | 40% | 0.1 s |
| Hybrid RRF + reranker | 78% | 88% | 95% | 95% | 0.841 | 100% | 100% | 80% | 14.0 s |

### Early refusal gate (top reranker score below threshold)

| Threshold | Unanswerable refused | Answerable wrongly refused |
|---|---|---|
| 0.005 | 10% | 0% |
| 0.01 | 20% | 0% |
| 0.02 | 20% | 5% |
| 0.05 | 60% | 5% |
| 0.1 | 70% | 8% |
| 0.2 | 70% | 8% |
| 0.3 | 70% | 8% |
| 0.5 | 90% | 10% |

## End-to-end answers (default pipeline)

Config: {'mode': 'hybrid_rerank', 'tokenizer': 'kiwi', 'k': 5, 'rewrite': True, 'model': 'gemini-3.5-flash-lite', 'min_rerank_score': 0.05, 'embed': 'gpahal/bge-m3-onnx-int8', 'rerank_match_lang': True, 'prompt': '2'}

| Metric | Value |
|---|---|
| Answer correct (all answerable) | 95% |
| Answer correct (when it answered) | 100% |
| Citation grounded (a cited passage has the evidence) | 100% |
| Faithful (LLM judge, 38 answers) | 100% |
| Unanswerable correctly refused | 90% |
| Answerable wrongly refused | 5% |
| Retrieval R@5 with query translation | 100% (cross-lingual 100%) |
| Answer in the question's language | 100% |
| Median total time | 15.1 s |

Mean time per stage: rewrite 1.5 s, retrieve_bm25 0.1 s, retrieve_vector 0.4 s, retrieve_fusion 0.0 s, retrieve_rerank 11.0 s, generate 1.8 s

## Before and after the error-analysis fixes

Baseline config: {'mode': 'hybrid_rerank', 'tokenizer': 'kiwi', 'k': 5, 'rewrite': True, 'model': 'gemini-3.5-flash-lite', 'min_rerank_score': 0.05, 'embed': 'gpahal/bge-m3-onnx-int8'}

| Metric | Baseline | Now |
|---|---|---|
| Answer correct | 80% | 95% |
| Faithful (judge) | 100% | 100% |
| Citation grounded | 97% | 100% |
| Answer in the question's language | 76% | 100% |
| Unanswerable refused | 100% | 90% |
| Answerable wrongly refused | 8% | 5% |

