# New User Setup Guide

This is the fastest path to a working local setup.

Related docs:

- [Documentation Index](INDEX.md)
- [Model Setup](MODEL_SETUP.md)
- [Citation Lookup Guide](CITATION_LOOKUP.md)
- [WSL Launcher](WSL_LAUNCHER.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## 1) Prerequisites

- Conda (Miniconda or Anaconda)
- Docker with daemon running
- Python 3.11 via the repo environment file

Create the supported environment:

```bash
[ -d "$HOME/.conda/envs/researchassistant" ] || conda env create -f environment.yml
conda activate researchassistant
```

If the environment already exists, refresh it with:

```bash
conda env update -n researchassistant -f environment.yml --prune
```

## 2) Configure `.env`

```bash
[ -f .env ] || cp .env.example .env
```

Set at minimum:

- `OPENAI_API_KEY=<your key>`
- `METADATA_BACKEND=zotero`
- `ZOTERO_REQUIRE_PERSISTENT_ID=1`
- `ZOTERO_DB_PATH=<path to zotero.sqlite>`
- `ZOTERO_STORAGE_ROOT=<path to Zotero storage>`
- optional WebDAV fallback for Zotero-managed attachments:
  - `ZOTERO_WEBDAV_URL=<base WebDAV URL containing Zotero attachment zips>`
  - `ZOTERO_WEBDAV_USERNAME=<webdav username>`
  - `ZOTERO_WEBDAV_PASSWORD=<webdav password>`
  - `ZOTERO_WEBDAV_CACHE_DIR=data/zotero_webdav_cache`
- `QWEN3_MODEL_PATH=<path to local Qwen/Qwen3-4B-Instruct-2507 base model>`

Optional API auth:

- `API_BEARER_TOKEN=<token>`

Edit `.env` and set the required values before running preflight or startup.

### Zotero WebDAV fallback setup

Use this when Zotero-managed attachments are not reliably accessible from the local runtime.

1. Add these to `.env`:
   - `ZOTERO_WEBDAV_URL=<base WebDAV URL containing Zotero attachment zip files>`
   - `ZOTERO_WEBDAV_USERNAME=<webdav username>`
   - `ZOTERO_WEBDAV_PASSWORD=<webdav password>`
   - `ZOTERO_WEBDAV_CACHE_DIR=data/zotero_webdav_cache`
   - optional linked-file mapping:
     - `ZOTERO_LINKED_PATH_MAP_JSON={"\\\\192.168.0.37\\pooled\\media\\Books\\pdfs":"/mnt/pooled/media/Books/pdfs"}`
2. Restart the API after saving `.env`.
3. Re-run `Sync + Ingest`.
4. The sync resolver will now try:
   - local Zotero storage first
   - WebDAV cache/download fallback for Zotero-managed `storage:` attachments
5. Check sync output fields:
   - `zotero_path_resolver_counts`
   - `zotero_path_issue_counts`

Limits:

- WebDAV fallback is intended for Zotero-managed stored attachments.
- Linked files can be fixed with `ZOTERO_LINKED_PATH_MAP_JSON` when a stable local mirror path exists.
- Unrelated remote URL attachments still need separate handling.

## 3) Download the LoRA adapter

Use the published release asset and setup steps in [Model Setup](MODEL_SETUP.md).

Recommended base-model version for current repo usage:

- `Qwen/Qwen3-4B-Instruct-2507`

## 4) Start services

For a local repo-hosted setup, use `ra` directly once the environment is active:

```bash
ra preflight
ra start
ra status
```

If you prefer the repo wrapper from PowerShell:

```powershell
.\tasks.ps1 preflight
.\tasks.ps1 start
.\tasks.ps1 status
```

If you want the direct repo wrapper from PowerShell:

```powershell
.\scripts\run_ra_from_repo.ps1 preflight
.\scripts\run_ra_from_repo.ps1 start
.\scripts\run_ra_from_repo.ps1 status
```

If you prefer the installed `ra` launcher from WSL but want to target the local service explicitly:

```bash
ra --base-url http://127.0.0.1:8001 start
ra --base-url http://127.0.0.1:8001 status
```

## 5) Use the web GUI

1. In **System**, enter a bearer token only if backend auth is enabled.
2. Click **Refresh Health**.
3. In **Sync + Ingest**, use:
   - `Source Mode = Zotero DB`
   - `Run ingest after sync = on`
   - `Skip already ingested PDFs = on`
4. Click **Run Sync + Ingest**.
5. Check the sync result for MinerU note coverage fields:
   - `zotero_mineru_notes_attached`
   - `zotero_mineru_notes_missing`
   - `zotero_mineru_notes_attached_for_ingest_candidates`
   - `zotero_mineru_notes_missing_for_ingest_candidates`
   - `zotero_mineru_notes_coverage_percent`
6. Use **Search** after ingest completes.

### Zotero plugin workflow for linked PDFs

If your Zotero library still uses linked PDF attachments:

1. Select the affected parent items or linked PDF attachments in Zotero.
2. Run `Tools > RAG Sync > Normalize Linked PDFs To Stored Attachments`.
3. Let Zotero complete its normal file sync to WebDAV.
4. Then run `Sync + Ingest` again from the web UI or Zotero plugin.

The intended default ingest entrypoint is now Zotero-backed (`source_mode = zotero_db`), not generic filesystem discovery.
The attachment acquisition layer resolves PDFs in this order: local Zotero storage, attachment overrides, WebDAV cache/fetch for `storage:` attachments, linked-path mappings, then unresolved-path diagnostics.

Progress overlay behavior in the plugin:

- while running: `Run in Background` and `Cancel Sync`
- after completion/failure/cancel: `Close`

## 6) Quick checks

Preferred CLI checks:

```bash
ra status
ra diagnostics
ra sync dry-run
ra zotero-search "query text"
```

If you want to target `home2` explicitly:

```bash
ra --base-url http://192.168.0.37:8001 status
```

Raw API checks still work when needed:

- health endpoint:

```bash
curl -s http://127.0.0.1:8001/api/health | python -m json.tool
```

- dry-run anti-join sync:

```bash
curl -s -X POST http://127.0.0.1:8001/api/sync \
  -H 'Content-Type: application/json' \
  -d '{"dry_run":true,"source_mode":"zotero_db","run_ingest":false}' | python -m json.tool
```
