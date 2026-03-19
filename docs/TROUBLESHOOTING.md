# Troubleshooting

## Zotero DB path missing

Set:

- `ZOTERO_DB_PATH=/path/to/zotero.sqlite`

## Zotero storage path missing

Set:

- `ZOTERO_STORAGE_ROOT=/path/to/Zotero/storage`

Optional fallback for Zotero-managed attachment downloads:

- `ZOTERO_WEBDAV_URL=...`
- `ZOTERO_WEBDAV_USERNAME=...`
- `ZOTERO_WEBDAV_PASSWORD=...`
- `ZOTERO_WEBDAV_CACHE_DIR=data/zotero_webdav_cache`

Notes:

- This fallback is for Zotero-managed `storage:` attachments.
- Linked Windows/UNC files can be mapped with `ZOTERO_LINKED_PATH_MAP_JSON` if you have a stable local mirror path.
- Best long-term fix for linked files: in Zotero, select the affected items and run `Tools > RAG Sync > Normalize Linked PDFs To Stored Attachments`, then let Zotero sync those stored files to WebDAV.
- It does not resolve unrelated remote URLs.
- After updating `.env`, restart the API before retrying sync.

## Zotero plugin progress window has no obvious exit

Current behavior:

- While work is running, the plugin overlay shows `Run in Background` and `Cancel Sync`
- Once the job completes, fails, or is cancelled, the overlay shows `Close`

If you still do not see `Close`, restart Zotero so it reloads the latest plugin XPI.

## Anystyle not running

Start it with:

```bash
docker compose up -d anystyle
```

## Qwen model or LoRA not found

Set:

- `QWEN3_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH`

See:

- [Model Setup](MODEL_SETUP.md)

## API bearer token mismatch

- If `API_BEARER_TOKEN` is set in `.env`, enter the same token in the web UI System panel.
- If auth is not needed, leave both unset.

## Docker or Neo4j not reachable

Run:

```bash
make preflight
docker compose up -d neo4j
```

Then refresh health in the UI.
