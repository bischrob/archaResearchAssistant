# Zotero RAG Sync Plugin (Rapid v1)

This plugin watches **My Library** item changes, ensures a Better BibTeX citation key exists, and triggers incremental RAG ingest via existing backend endpoints.

## Features

- Watches Zotero item changes (`add`, `modify`, `refresh`) for **My Library**.
- Dedupe queue with debounce (default 15s).
- Better BibTeX citekey extraction and stamping into item `Extra` as `Citation Key: <key>`.
- Backend calls:
  - `POST /api/sync` (combined sync + ingest into Neo4j by default)
  - `POST /api/ingest` (`mode=custom`, changed PDF absolute paths)
  - `GET /api/ingest/status` polling
- Tools menu actions:
  - `RAG Sync: Sync Now`
  - `RAG Sync: Cancel Running Sync`
  - `RAG Sync: Retry Failed`
  - `RAG Sync: Pause/Resume`
  - `RAG Sync: Show Diagnostics`
- `Sync Now` now opens a centered in-app progress overlay and shows an explicit error alert if backend sync fails.
- `Sync Now` now polls `/api/sync/status` and displays live progress updates from backend status messages (including current filename when provided).
- If you dismiss the overlay with `Run in Background`, the plugin stays in the running state until the backend reaches a terminal state. Use `Cancel Running Sync` to stop a background sync.
- Sync source supports ZIP-backed libraries: backend can scan ZIP files and surface embedded PDFs.
- In current workflow, `Sync Now` triggers ingest into Neo4j as part of `/api/sync` unless backend `dry_run` is enabled.

## Required backend env

- `API_BEARER_TOKEN` (optional; if set, plugin must send matching bearer token)

## Plugin prefs (stored in Zotero prefs)

- `extensions.zotero-rag-sync.backendURL` (default `http://127.0.0.1:8000`)
- `extensions.zotero-rag-sync.bearerToken`
- `extensions.zotero-rag-sync.sourceMode` (`zotero_db` or `filesystem`, default `zotero_db`)
- `extensions.zotero-rag-sync.sourceDir` (default empty; set this only for filesystem mode)
- `extensions.zotero-rag-sync.debounceSeconds` (default `15`)
- `extensions.zotero-rag-sync.paused` (default `false`)

## Notes

- Better BibTeX is required in this v1 implementation.
- Group libraries are intentionally ignored in this rapid version.
- Zotero 8 rejects this add-on as invalid if `applications.zotero.update_url` is missing in `manifest.json`.
- If your Zotero build requires a different plugin packaging format, keep this runtime logic and adapt only packaging/manifest glue.
