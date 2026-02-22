# Test Suite Overview

## Test files
- `tests/test_pipeline.py`
- `tests/test_retrieval.py`
- `tests/test_paperpile_metadata.py`
- `tests/test_web_api.py`

## Coverage focus
- PDF selection and ingest summary behavior.
- Query parsing and retrieval/reranking behavior.
- Paperpile metadata matching robustness.
- FastAPI endpoint flows with monkeypatched dependencies.

## Execution prerequisites
- Python path must include project root (`PYTHONPATH=.`) for direct `src.*` imports.
- Without this, collection fails with `ModuleNotFoundError: src`.

## Current characteristics
- Mostly unit-style tests with fake stores/mocks.
- No integration tests against live Neo4j or live OpenAI.
- No frontend JS unit tests.

## Gaps
- No test asserting DB schema migration correctness end-to-end.
- No test for real `rclone` sync behavior.
- No stress/performance tests for large corpus ingest/query.

## Related
- [[50_Testing/02_current_test_status_2026-02-21]]
- [[60_Troubleshooting/02_known_risks_and_debt]]
