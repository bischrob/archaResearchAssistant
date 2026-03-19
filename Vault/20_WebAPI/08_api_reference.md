# API Reference

Last reviewed: 2026-03-19
Source of truth: `webapp/main.py`
Base URL: `http://127.0.0.1:8000`

## Authentication
- Token auth is conditional.
- If `API_BEARER_TOKEN` is unset, protected endpoints are open.
- If `API_BEARER_TOKEN` is set, send `Authorization: Bearer <token>`.

Protected endpoints:
- `POST /api/sync`
- `GET /api/sync/status`
- `POST /api/sync/stop`
- `POST /api/ingest`
- `POST /api/ingest/preview`
- `GET /api/ingest/status`
- `POST /api/ingest/stop`
- `POST /api/query`
- `GET /api/query/status`
- `POST /api/query/stop`

Unprotected endpoints:
- `GET /`
- `GET /api/health`
- `GET /api/diagnostics`
- `GET /api/article/{citekey}`
- `POST /api/articles/by-citekeys`
- `POST /api/ask`
- `POST /api/ask/export`

## Job Lifecycle (Sync/Ingest/Query)
Job endpoints return a shared shape:
- `status`: `idle|running|completed|failed|cancelled`
- `lifecycle_state`: same as status, except running+cancel-requested reports `cancelling`
- `terminal_reason`: `completed|failed|cancelled|null`
- `cancel_requested`: `true|false`
- `stop_state`: `accepted|noop_idle|noop_terminal|noop_cancelling|null`
- `request_id`: UUID for current run
- `progress_percent`: `0..100`
- `progress_message`: human-readable progress detail
- `result`: endpoint-specific payload when completed
- `error`: failure text when failed

## Endpoint Summary

### Health and Diagnostics
- `GET /api/health`
  - Returns service status + Neo4j graph counts.
- `GET /api/diagnostics`
  - Returns multi-check diagnostics (metadata source, sync script, API key presence, metadata coverage, PDF header sample, Neo4j connectivity).

### Sync
- `POST /api/sync`
  - Request fields:
    - `dry_run` (bool)
    - `source_dir` (string path)
    - `source_mode` (`filesystem|zotero_db`)
    - `run_ingest` (bool)
    - `ingest_skip_existing` (bool)
  - Behavior:
    - Collects PDFs from filesystem/ZIPs or Zotero DB attachment paths.
    - Computes metadata match summary.
    - Optionally runs ingest in same job when `run_ingest=true` and `dry_run=false`.
- `GET /api/sync/status`
- `POST /api/sync/stop`

### Ingest
- `POST /api/ingest`
  - Request fields:
    - `mode` (`batch|all|custom|test3`)
    - `source_dir` (string path)
    - `pdfs` (list of explicit paths for custom mode)
    - `override_existing` (bool)
    - `partial_count` (int)
  - Behavior:
    - `test3` is normalized to `batch`.
    - `all` runs sequential batches of size `partial_count`.
    - Returns aggregate + per-batch parsing/ingest stats.
- `POST /api/ingest/preview`
  - Preview rows include `exists_in_graph`, `will_ingest`, and metadata fields.
- `GET /api/ingest/status`
- `POST /api/ingest/stop`

### Article Lookup
- `GET /api/article/{citekey}`
  - Optional query param: `chunk_limit` (1..20, default 3).
- `POST /api/articles/by-citekeys`
  - Request fields:
    - `citekeys` (list, deduped case-insensitively)
    - `chunk_limit` (1..20)

### Query
- `POST /api/query`
  - Request fields:
    - `query` (non-empty)
    - `limit` (1..20, default 20)
    - `limit_scope` (`papers|chunks`, default `papers`)
    - `chunks_per_paper` (1..20, default 8)
  - Returns ranked retrieval results.
- `GET /api/query/status`
- `POST /api/query/stop`

### Ask (RAG Answer)
- `POST /api/ask`
  - Request fields:
    - `question` (non-empty)
    - `rag_results` (1..30)
    - `model` (optional)
    - `enforce_citations` (bool)
    - `preprocess_search` (bool)
  - Behavior:
    - Optional query rewrite.
    - Retrieval in chunk mode.
    - LLM answer with citation audit metadata.

- `POST /api/ask/export`
  - Request fields:
    - `report` (ask response payload)
    - `format` (`markdown|csv|pdf`)

## Minimal Examples

### Start sync
```bash
curl -X POST http://127.0.0.1:8000/api/sync \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -d '{"source_mode":"zotero_db","run_ingest":true,"dry_run":false}'
```

### Poll sync status
```bash
curl http://127.0.0.1:8000/api/sync/status \
  -H "Authorization: Bearer $API_BEARER_TOKEN"
```

### Targeted custom ingest
```bash
curl -X POST http://127.0.0.1:8000/api/ingest \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -d '{
    "mode":"custom",
    "source_dir":"/mnt/c/Users/rjbischo/Zotero/storage",
    "pdfs":["/mnt/c/Users/rjbischo/Zotero/storage/ABC123/file.pdf"],
    "override_existing":true,
    "partial_count":30
  }'
```

### Query with paper scope and 8 chunks per paper
```bash
curl -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $API_BEARER_TOKEN" \
  -d '{
    "query":"copyright and generative ai training",
    "limit":20,
    "limit_scope":"papers",
    "chunks_per_paper":8
  }'
```

## Related
- [[20_WebAPI/01_api_surface]]
- [[20_WebAPI/02_job_manager]]
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
- [[20_WebAPI/05_query_and_ask_api]]
