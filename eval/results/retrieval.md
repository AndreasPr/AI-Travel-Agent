# Retrieval evaluation
Labeled queries: 1

| mode | recall@1 | recall@3 | recall@5 | recall@10 | mrr | ndcg@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| vector | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| bm25 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hybrid | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hybrid+rerank | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| hybrid+rerank+filters | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

Mode definitions:
- vector: search(..., mode='vector', rerank=False, auto_filters=False, expand_queries=False)
- bm25: search(..., mode='bm25', rerank=False, auto_filters=False, expand_queries=False)
- hybrid: search(..., mode='hybrid', rerank=False, auto_filters=False, expand_queries=False)
- hybrid+rerank: search(..., mode='hybrid', rerank=True, auto_filters=False, expand_queries=False)
- hybrid+rerank+filters: search(..., mode='hybrid', rerank=True, auto_filters=True, expand_queries=True, city=..., country=..., season=None, topic=None)
