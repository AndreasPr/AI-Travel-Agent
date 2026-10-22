# Retrieval evaluation
Labeled queries: 8

| mode | recall@1 | recall@3 | recall@5 | recall@10 | mrr | ndcg@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| vector | 0.7500 | 0.8750 | 0.8750 | 0.9375 | 1.0000 | 0.9206 |
| bm25 | 0.3125 | 0.3125 | 0.3750 | 0.3750 | 0.5000 | 0.3879 |
| hybrid | 0.7500 | 0.8750 | 0.9375 | 1.0000 | 1.0000 | 0.9536 |
| hybrid+rerank | 0.7500 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9799 |
| hybrid+rerank+filters | 0.7500 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 0.9799 |

Mode definitions:
- vector: search(..., mode='vector', rerank=False, auto_filters=False, expand_queries=False)
- bm25: search(..., mode='bm25', rerank=False, auto_filters=False, expand_queries=False)
- hybrid: search(..., mode='hybrid', rerank=False, auto_filters=False, expand_queries=False)
- hybrid+rerank: search(..., mode='hybrid', rerank=True, auto_filters=False, expand_queries=False)
- hybrid+rerank+filters: search(..., mode='hybrid', rerank=True, auto_filters=True, expand_queries=True, city=..., country=..., season=None, topic=None)
