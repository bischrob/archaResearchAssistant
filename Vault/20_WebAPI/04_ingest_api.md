# Web API: Ingest Endpoints

## Source file
- `webapp/main.py` (`/api/ingest*`)

## Endpoints
- `POST /api/ingest`
- `POST /api/ingest/preview`
- `GET /api/ingest/status`
- `POST /api/ingest/stop`

## Ingest request behavior
- Accepts modes: `batch`, `all`, `custom`, `test3`.
- `test3` is normalized to `batch`.
- `override_existing` toggles existing-article skip behavior.
- `partial_count` controls first-N for `batch` and batch size for `all`.

## `all` mode specifics
- Selected files are chunked into sequential batches of size `partial_count`.
- Partial progress and partial summary written after each batch.

## Preview endpoint
- Resolves candidate set with and without metadata filtering.
- Annotates each row with:
  - exists in graph
  - will ingest
  - metadata presence and key fields

## Failure modes
- Invalid mode/params rejected by Pydantic.
- Empty post-filter candidate set can raise user-facing `ValueError` details.
- Neo4j unavailable may impact existing-ID checks and preview stats.

## Related
- [[10_Backend/04_ingest_pipeline_module]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
