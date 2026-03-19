# New User Setup Guide

This guide is the fastest path to a working local setup.

Related docs:

- [Documentation Index](INDEX.md)
- [Model Setup](MODEL_SETUP.md)
- [Anystyle Setup](ANYSTYLE_SETUP.md)
- [Citation Lookup Guide](CITATION_LOOKUP.md)
- [Troubleshooting](TROUBLESHOOTING.md)

## 1) Prerequisites

- Python 3.10+
- Docker with daemon running
- `pip install -r requirements.txt`

## 2) Configure `.env`

```bash
cp .env.example .env
```

Set at minimum:

- `OPENAI_API_KEY=<your key>`
- `METADATA_BACKEND=zotero`
- `ZOTERO_DB_PATH=<path to zotero.sqlite>`
- `ZOTERO_STORAGE_ROOT=<path to Zotero storage>`
- `QWEN3_MODEL_PATH=<path to local Qwen3 base model>`

Optional API auth:

- `API_BEARER_TOKEN=<token>` (required only if you want secured `/api/*` endpoints)

## 3) Download the LoRA adapter

Use the published release asset and setup steps in [Model Setup](MODEL_SETUP.md).

## 4) Install and enable Anystyle

Use the build, runtime, and fallback guidance in [Anystyle Setup](ANYSTYLE_SETUP.md).

## 5) Start services

```bash
make preflight
make start
```

## 6) Use the web GUI

1. In **System**, enter bearer token only if backend auth is enabled.
2. Click **Refresh Health**.
3. In **Sync + Ingest**, use:
   - `Source Mode = Zotero DB`
   - `Run ingest after sync = on`
   - `Skip already ingested PDFs = on`
4. Click **Run Sync + Ingest**.
5. Use **Search** after ingest completes.

## 7) Quick checks

- Health endpoint:
  - `curl -s http://127.0.0.1:8000/api/health | python -m json.tool`
- Dry-run anti-join sync:
  - `curl -s -X POST http://127.0.0.1:8000/api/sync -H 'Content-Type: application/json' -d '{"dry_run":true,"source_mode":"zotero_db","run_ingest":false}' | python -m json.tool`
