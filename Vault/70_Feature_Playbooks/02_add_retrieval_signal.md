# Playbook: Add a New Retrieval Signal

## Goal
Add an additional retrieval channel or reranking feature.

## Preferred insertion points
- New store query method in `src/rag/neo4j_store.py`.
- Merge logic in `contextual_retrieve` (`src/rag/retrieval.py`).
- Weighting in `rerank_hits`.

## Steps
1. Define signal contract (input, score scale, output fields).
2. Implement query method in `GraphStore` returning chunk-level rows.
3. Merge into `by_chunk` map with controlled score normalization.
4. Expose source tag in `retrieval_sources`.
5. Extend `query_features` if signal should be explainable.
6. Add targeted unit tests in `tests/test_retrieval.py`.

## Guardrails
- Avoid score domination by a single channel.
- Keep missing-signal behavior graceful.
- Maintain deterministic ordering for equal scores where possible.

## Validation checklist
- Existing tests still pass.
- New signal visible in returned results and UI output.
- Query latency remains acceptable.
