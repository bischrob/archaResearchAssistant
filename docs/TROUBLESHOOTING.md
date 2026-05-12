# Troubleshooting

## `ra` is talking to the wrong host

There are two normal targets:

- local service: `http://127.0.0.1:8001`
- `home2`: `http://192.168.0.37:8001`

Rules of thumb:

- `python scripts/ra.py ...` defaults to the local service
- the installed `ra` launcher defaults to `home2` when installed under WSL
- override either one with `RA_BASE_URL` or `--base-url`

Examples:

```bash
python scripts/ra.py --base-url http://192.168.0.37:8001 status
ra --base-url http://127.0.0.1:8001 status
RA_BASE_URL=http://127.0.0.1:8001 ra diagnostics
```

If the launcher still points somewhere unexpected, rerun:

```bash
./scripts/install_wsl_ra_launcher.sh
```

## Zotero DB path missing

Set:

- `ZOTERO_DB_PATH=/path/to/zotero.sqlite`

## Zotero storage path missing

Set:

- `ZOTERO_STORAGE_ROOT=/path/to/Zotero/storage`

## Zotero PDF Browser shows a JSON parse error

If the UI shows:

- `JSON.parse: unexpected character at line 1 column 1 of the JSON data`

the browser received a non-JSON error response from the API. The usual causes are:

- `ZOTERO_DB_PATH` is unset or points to a missing `zotero.sqlite`
- `ZOTERO_STORAGE_ROOT` is unset or points to the wrong Zotero `storage/` directory
- a resolver or backend dependency failed before the API could build a normal response

Check:

```bash
make preflight
echo "$ZOTERO_DB_PATH"
echo "$ZOTERO_STORAGE_ROOT"
```

Then restart the web app and retry the Zotero browser search.

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

## Sync result shows low MinerU note coverage

The sync result now reports:

- `zotero_mineru_notes_attached`
- `zotero_mineru_notes_missing`
- `zotero_mineru_notes_attached_for_ingest_candidates`
- `zotero_mineru_notes_missing_for_ingest_candidates`

If the candidate-specific values are low, the ingestable PDFs do not yet have matching MinerU child notes attached in Zotero. The usual fixes are:

- push or regenerate MinerU child notes for the missing attachments
- verify the note has the expected MinerU marker/body format
- rerun `ra sync dry-run` before `ra sync ingest` to confirm the note counts improved

## Zotero plugin progress window has no obvious exit

Current behavior:

- while work is running, the plugin overlay shows `Run in Background` and `Cancel Sync`
- once the job completes, fails, or is cancelled, the overlay shows `Close`

If you still do not see `Close`, restart Zotero so it reloads the latest plugin XPI.

## Qwen model or LoRA not found

Set:

- `QWEN3_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH`

See [Model Setup](MODEL_SETUP.md).

## `/api/query` looks stalled or spends a long time at startup

Two different failure modes have shown up here:

1. cold embedder startup: creating a fresh `SentenceTransformer` for each query can make the first live query look hung
2. off-domain false positives: the request completes, but generic `points` matches swamp archaeology-specific papers

What changed in-repo:

- `GraphStore` now reuses a cached sentence-transformer embedder for identical model/device settings
- archaeology reranking now tracks `anchor_hits` and penalizes rows with no culture/place anchors when the query contains them
- a persistent live harness was added at `eval/archaeology_query_golden.json` and `scripts/run_live_query_golden.py`

Check the harness against your running API:

```bash
python3 scripts/run_live_query_golden.py --base-url http://127.0.0.1:8001
```

If the harness still shows old behavior, the running service is probably using an older environment or process image and needs to be restarted in the supported environment.

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
