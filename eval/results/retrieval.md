# Retrieval evaluation
Labeled queries: 29

| mode | recall@1 | recall@3 | recall@5 | recall@10 | mrr | ndcg@10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| vector | 0.5316 | 0.7011 | 0.7299 | 0.8592 | 0.8774 | 0.7804 |
| bm25 | 0.0632 | 0.1552 | 0.2701 | 0.3592 | 0.2073 | 0.2230 |
| hybrid | 0.2644 | 0.5057 | 0.6466 | 0.8621 | 0.5624 | 0.6009 |
| hybrid+rerank | 0.4511 | 0.7557 | 0.8448 | 0.8736 | 0.8017 | 0.7747 |
| hybrid+rerank+filters | 0.4684 | 0.6868 | 0.7644 | 0.7644 | 0.7960 | 0.7153 |

Mode definitions:
- vector: search(..., mode='vector', rerank=False, auto_filters=False, expand_queries=False)
- bm25: search(..., mode='bm25', rerank=False, auto_filters=False, expand_queries=False)
- hybrid: search(..., mode='hybrid', rerank=False, auto_filters=False, expand_queries=False)
- hybrid+rerank: search(..., mode='hybrid', rerank=True, auto_filters=False, expand_queries=False)
- hybrid+rerank+filters: search(..., mode='hybrid', rerank=True, auto_filters=True, expand_queries=True, city=..., country=..., season=None, topic=None)
