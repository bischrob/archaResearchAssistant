# Zotero RAG Sync Plugin (Rapid v1)

This plugin watches **My Library** item changes, ensures a Better BibTeX citation key exists, and triggers incremental RAG ingest via existing backend endpoints.

## Features

- Watches Zotero item changes (`add`, `modify`, `refresh`) for **My Library**.
- Dedupe queue with debounce (default 15s).
- Better BibTeX citekey extraction and stamping into item `Extra` as `Citation Key: <key>`.
- Backend calls:
  - `POST /api/sync`
  - `POST /api/ingest` (`mode=custom`, changed PDF absolute paths)
  - `GET /api/ingest/status` polling
- Tools menu actions:
  - `RAG Sync: Sync Now`
  - `RAG Sync: Retry Failed`
  - `RAG Sync: Pause/Resume`
  - `RAG Sync: Show Diagnostics`
- `Sync Now` now opens a visible progress window and shows an explicit error alert if backend sync fails.

## Required backend env

- `API_BEARER_TOKEN` (optional; if set, plugin must send matching bearer token)

## Plugin prefs (stored in Zotero prefs)

- `extensions.zotero-rag-sync.backendURL` (default `http://127.0.0.1:8000`)
- `extensions.zotero-rag-sync.bearerToken`
- `extensions.zotero-rag-sync.debounceSeconds` (default `15`)
- `extensions.zotero-rag-sync.paused` (default `false`)

## Notes

- Better BibTeX is required in this v1 implementation.
- Group libraries are intentionally ignored in this rapid version.
- Zotero 8 rejects this add-on as invalid if `applications.zotero.update_url` is missing in `manifest.json`.
- If your Zotero build requires a different plugin packaging format, keep this runtime logic and adapt only packaging/manifest glue.
