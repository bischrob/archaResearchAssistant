# Web API Surface

## Source file
- `webapp/main.py`

## Route inventory
- `GET /`
- `GET /api/health`
- `GET /api/diagnostics`
- `POST /api/sync`
- `GET /api/sync/status`
- `POST /api/sync/stop`
- `POST /api/ingest`
- `POST /api/ingest/preview`
- `GET /api/ingest/status`
- `POST /api/ingest/stop`
- `GET /api/article/{citekey}`
- `POST /api/articles/by-citekeys`
- `POST /api/query`
- `GET /api/query/status`
- `POST /api/query/stop`
- `POST /api/ask`
- `POST /api/ask/export`

## API style
- JSON request/response for most endpoints.
- Asynchronous operations return immediate job status and are polled.
- Errors surfaced via `HTTPException` (typically 400/404/409).
- Known-paper retrieval should prefer citekey endpoints over semantic query:
  - `GET /api/article/{citekey}`
  - `POST /api/articles/by-citekeys`

## Shared dependencies
- `Settings`
- `GraphStore`
- Ingest/retrieval/LLM helpers in `src/rag/`

## Request models
Defined via Pydantic classes in `webapp/main.py`:
- `SyncRequest`, `IngestRequest`, `QueryRequest`, `ArticleLookupRequest`, `AskRequest`, `AskExportRequest`, `IngestPreviewRequest`.

## Related
- [[20_WebAPI/02_job_manager]]
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
- [[20_WebAPI/05_query_and_ask_api]]
- [[20_WebAPI/08_api_reference]]
