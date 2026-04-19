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
  - `RAG Sync: Show External Note Bridge Diagnostics`
  - `RAG Sync: Normalize Linked PDFs To Stored Attachments`
- `Sync Now` now opens a centered in-app progress overlay and shows an explicit error alert if backend sync fails.
- `Sync Now` now polls `/api/sync/status` and displays live progress updates from backend status messages (including current filename when provided).
- If you dismiss the overlay with `Run in Background`, the plugin stays in the running state until the backend reaches a terminal state. Use `Cancel Running Sync` to stop a background sync.
- Once the overlay reaches a terminal state (`completed`, `failed`, or `cancelled`), it shows an explicit `Close` button.
- Sync source supports ZIP-backed libraries: backend can scan ZIP files and surface embedded PDFs.
- In current workflow, `Sync Now` triggers ingest into Neo4j as part of `/api/sync` unless backend `dry_run` is enabled.
- `Normalize Linked PDFs To Stored Attachments` operates on the current Zotero selection. It imports linked PDF attachments into Zotero-managed storage under the same parent item and deletes the old linked attachment only after the stored copy is created successfully.
- Best-practice workflow for WebDAV-backed sync:
  1. Select the items whose linked PDF attachments you want to normalize.
  2. Run `Tools > RAG Sync > Normalize Linked PDFs To Stored Attachments`.
  3. Let Zotero finish its normal file sync to WebDAV.
  4. Run `Sync Now` to ingest from Zotero-managed storage/WebDAV rather than external UNC paths.

## External note bridge

The plugin now registers local Zotero connector endpoints so outside tools can push
MinerU markdown into Zotero as structured child notes.

Endpoints on the local Zotero connector server:

- `GET http://127.0.0.1:23119/rag-sync/bridge/ping`
- `POST http://127.0.0.1:23119/rag-sync/bridge/import-mineru-note`

Security model:

- The bridge is disabled by default.
- You must set both:
  - `extensions.zotero-rag-sync.externalBridgeEnabled=true`
  - `extensions.zotero-rag-sync.externalBridgeToken=<long random token>`
- Requests must include `auth_token` in the JSON body.

Minimal POST payload:

```json
{
  "auth_token": "set-this-in-zotero-prefs",
  "attachment_key": "23LHAREP",
  "md_content": "# Parsed markdown\n..."
}
```

Behavior:

- `attachment_key` is matched against the Zotero attachment item key in `My Library`
- the plugin creates or updates a child note on the parent item
- note content is wrapped in the same MinerU metadata header format used by the repo's
  note-first ingest path (`LLM_FOR_ZOTERO_MINERU_NOTE_V1`, `attachment_id`,
  `parent_item_id`, `parsed_at`, `mineru_version`, `content_hash`)

Repo helper:

- `scripts/push_mineru_notes_via_zotero_bridge.py`

Example:

```bash
python scripts/push_mineru_notes_via_zotero_bridge.py \
  "C:\\Users\\rjbischo\\Nextcloud\\zotero" \
  --token "your-bridge-token"
```

## Required backend env

- `API_BEARER_TOKEN` (optional; if set, plugin must send matching bearer token)

## Plugin prefs (stored in Zotero prefs)

- `extensions.zotero-rag-sync.backendURL` (default `http://127.0.0.1:8001`)
- `extensions.zotero-rag-sync.bearerToken`
- `extensions.zotero-rag-sync.sourceMode` (`zotero_db` or `filesystem`, default `zotero_db`)
- `extensions.zotero-rag-sync.sourceDir` (default empty; set this only for filesystem mode)
- `extensions.zotero-rag-sync.debounceSeconds` (default `15`)
- `extensions.zotero-rag-sync.paused` (default `false`)
- `extensions.zotero-rag-sync.externalBridgeEnabled` (default `false`)
- `extensions.zotero-rag-sync.externalBridgeToken` (default empty)

## Notes

- Better BibTeX is required in this v1 implementation.
- Group libraries are intentionally ignored in this rapid version.
- Zotero 8 rejects this add-on as invalid if `applications.zotero.update_url` is missing in `manifest.json`.
- If your Zotero build requires a different plugin packaging format, keep this runtime logic and adapt only packaging/manifest glue.
