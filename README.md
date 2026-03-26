# archaResearch Asssistant

archaResearch Asssistant is a Neo4j-backed PDF ingest and retrieval system with a web UI, Zotero-aware sync, citation parsing, and grounded search workflows.

## Start Here

- New user setup: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Documentation hub: [docs/INDEX.md](docs/INDEX.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Anystyle setup: [docs/ANYSTYLE_SETUP.md](docs/ANYSTYLE_SETUP.md)
- Citation-first lookup: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Operator CLI runbook: [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md)

## Included vs Excluded

Included in GitHub:

- application source
- tests
- scripts
- Zotero plugin scaffold
- public documentation

Excluded from GitHub:

- PDFs
- Neo4j runtime data
- local models
- logs
- `.env`
- local Vault notes
- Zotero debug logs

## LoRA Release Asset

Recommended citation-extraction LoRA:

- https://github.com/bischrob/archaResearchAssistant/releases/tag/lora-20260319-104710

## Recommended Parsing Architecture

Current production ingest is aligned to:

- heuristics for section/reference detection
- OpenClaw-agent repair for ambiguous reference blocks
- Anystyle for structured citation parsing from one-reference-per-line text

Recommended runtime setting:

- `CITATION_PARSER=openclaw_refsplit_anystyle`

## Supported Setup Matrix

- OS: Linux and WSL are the primary documented environments
- Docker: required
- Neo4j: required
- Zotero backend: recommended default
- GPU: optional
- OpenAI API key: required for grounded LLM answer flows
- OpenClaw agent command: recommended for ambiguous reference reconstruction during ingest

## Golden-query live harness

Persistent archaeology-style live query checks now live in:

- `eval/archaeology_query_golden.json`
- `scripts/run_live_query_golden.py`

Run them against a running web API instance:

```bash
python3 scripts/run_live_query_golden.py --base-url http://192.168.0.37:8001
```

The current golden set is intentionally aimed at false-positive regressions around generic `points`/`projectile points` matches.

## Quickstart

```bash
conda env create -f environment.yml
conda activate researchassistant
cp .env.example .env
make preflight
pip install -e .
ra start
ra status
make smoke
```

## Operator CLI

The repo now ships a first-party operator CLI with an installable `ra` entrypoint for the common daily workflows that previously required raw curl payloads. The legacy `python scripts/ra.py ...` path still works as a thin wrapper, but the preferred repo-native install path is:

```bash
pip install -e .
ra status
ra diagnostics
ra sync dry-run
ra sync ingest
ra zotero-search "transformer"
ra zotero-ingest ABC123XYZ
ra query "household archaeology"
ra ask "What do recent papers say about household resilience?"
ra article shawThinkingFastSlowArtificial2026
```

Notes:

- The default ra API target is http://192.168.0.37:8001 (home2). Override with RA_BASE_URL or --base-url when needed.
- `ra start` now resolves Python deterministically: repo `.venv` first, then active virtual/conda envs, then named conda envs, then PATH Python.
- The supported local Python target is currently **Python 3.11+**.
- `requirements.txt` is configured to use the PyTorch CUDA 12.4 wheel index.
- The ingest pipeline now requires **real sentence-transformer embeddings**; hash-placeholder embeddings are disabled.

For full setup, including Zotero, LoRA, and Anystyle:

- [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- [docs/WSL_LAUNCHER.md](docs/WSL_LAUNCHER.md)

## Core Workflow

1. Configure `.env` with your OpenAI key and Zotero paths.
2. Start the stack with `make start`.
3. Open the web UI and use `Sync + Ingest` for anti-join syncs, or `Zotero PDF Browser` to search available Zotero-backed PDFs and ingest or re-ingest selected items.
4. Use `Search` for paper or chunk retrieval.

## Zotero WebDAV Fallback

If Zotero-managed attachments are not locally reachable from the runtime, you can configure WebDAV fallback in [`.env.example`](/home/rjbischo/researchAssistant/.env.example):

- `ZOTERO_WEBDAV_URL`
- `ZOTERO_WEBDAV_USERNAME`
- `ZOTERO_WEBDAV_PASSWORD`
- `ZOTERO_WEBDAV_CACHE_DIR`

The resolver order is:

1. local Zotero storage
2. cached/downloaded WebDAV copy for Zotero-managed `storage:` attachments
3. linked-file resolution via stable local path mappings when configured
4. unresolved path classification for anything still inaccessible

See:

- [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## Plugin

The Zotero plugin scaffold lives in:

- `plugins/zotero-rag-sync/`

It can trigger the combined backend sync and ingest workflow and supports bearer-token auth when enabled.

Plugin workflow notes:

- `Sync Now` opens a progress overlay with:
  - `Run in Background` while work is still running
  - `Cancel Sync` while work is still running
  - `Close` once the run has completed, failed, or been cancelled
- `Import PDF URL To Stored Attachment` prompts for a PDF URL and imports it as a Zotero-managed stored attachment under the currently selected parent item. This is the direct path for making a remote PDF eligible for Zotero file sync/WebDAV without creating a linked URL attachment.
- `Normalize Linked PDFs To Stored Attachments` converts selected linked PDF attachments into Zotero-managed stored attachments under the same parent item. This is the recommended way to migrate away from UNC/linked-file paths before relying on WebDAV-backed sync.

## Testing

Project-local test environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install pytest numpy PyMuPDF neo4j requests fastapi starlette httpx pydantic pyyaml
```

Run the suite:

```bash
pytest -q
make test-unit
make test-e2e   # live full-stack tests remain gated behind RUN_E2E=1
make smoke
```

Notes:

- The default test suite now runs as real pytest tests rather than compile-only checks.
- New integration coverage exercises Zotero-first identity enforcement, attachment resolver provenance, text-acquisition provenance, section-aware structured extraction, `.references.txt` sidecar generation, Neo4j reference-ingest behavior, and the Zotero PDF browser/API ingest path with lightweight mocks only at external boundaries.

## Local Conveniences

- Auto-versioning can be enabled locally with:

```bash
git config core.hooksPath .githooks
```

- Optional daily Dropbox sync helper:

```bash
scripts/rclone_sync_dropbox.sh
```
