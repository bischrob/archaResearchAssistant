# archaResearch Assistant

archaResearch Assistant is a Neo4j-backed PDF ingest and retrieval system with a web UI, Zotero-aware sync, citation parsing, and grounded search workflows.

## Start here

- New user setup: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Documentation hub: [docs/INDEX.md](docs/INDEX.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Anystyle setup: [docs/ANYSTYLE_SETUP.md](docs/ANYSTYLE_SETUP.md)
- Citation-first lookup: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Operator CLI runbook: [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md)
- WSL launcher notes: [docs/WSL_LAUNCHER.md](docs/WSL_LAUNCHER.md)

## Included vs excluded

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

## LoRA release asset

Recommended citation-extraction LoRA:

- <https://github.com/bischrob/archaResearchAssistant/releases/tag/lora-20260319-104710>

## Recommended parsing architecture

Current production ingest is aligned to:

- heuristics for section/reference detection
- OpenClaw-agent repair for ambiguous reference blocks
- Anystyle for structured citation parsing from one-reference-per-line text

Recommended runtime setting:

- `CITATION_PARSER=openclaw_refsplit_anystyle`

## Supported setup matrix

- OS: Linux and WSL are the primary documented environments
- Docker: required
- Neo4j: required
- Zotero backend: recommended default
- GPU: optional
- OpenAI API key: required for grounded LLM answer flows
- OpenClaw agent command: recommended for ambiguous reference reconstruction during ingest

## Golden-query live harness

Persistent archaeology-style live query checks live in:

- `eval/archaeology_query_golden.json`
- `scripts/run_live_query_golden.py`

Run them against a local API instance:

```bash
python3 scripts/run_live_query_golden.py --base-url http://127.0.0.1:8001
```

Or point them at `home2` explicitly:

```bash
python3 scripts/run_live_query_golden.py --base-url http://192.168.0.37:8001
```

The current golden set is intentionally aimed at false-positive regressions around generic `points` / `projectile points` matches.

## Quickstart

```bash
conda env create -f environment.yml
conda activate researchassistant
cp .env.example .env
make preflight
pip install -e .
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
make smoke
```

## Operator CLI

The repo ships a first-party operator CLI with an installable `ra` entrypoint for the common daily workflows that previously required raw curl payloads.

Preferred direct repo usage:

```bash
./scripts/run_ra_from_repo.sh status
./scripts/run_ra_from_repo.sh diagnostics
./scripts/run_ra_from_repo.sh sync dry-run
./scripts/run_ra_from_repo.sh sync ingest
./scripts/run_ra_from_repo.sh zotero-search "transformer"
./scripts/run_ra_from_repo.sh zotero-ingest ABC123XYZ
./scripts/run_ra_from_repo.sh query "household archaeology"
./scripts/run_ra_from_repo.sh ask "What do recent papers say about household resilience?"
./scripts/run_ra_from_repo.sh article shawThinkingFastSlowArtificial2026
```

Launcher/default-target notes:

- Direct repo wrapper (`./scripts/run_ra_from_repo.sh ...`) defaults to `http://127.0.0.1:8001`.
- The installed `ra` launcher from `scripts/install_wsl_ra_launcher.sh` is opinionated by environment:
  - on WSL it defaults to `http://192.168.0.37:8001` (`home2`)
  - on non-WSL Linux it defaults to `http://127.0.0.1:8001`
- Override either path with `RA_BASE_URL` or `--base-url` whenever you want a different target.
- `python scripts/ra.py ...` works inside an activated environment or after `pip install -e .`, but the shell wrapper above is the more environment-agnostic repo entrypoint.
- If you already installed `ra`, rerun `scripts/install_wsl_ra_launcher.sh` after launcher changes so the generated wrapper matches the current repo behavior.
- `ra start` and `./scripts/run_ra_from_repo.sh start` reuse `./start.sh` and resolve Python deterministically: repo `.venv` first, then active virtual/conda envs, then named conda envs, then PATH Python.
- The supported local Python target is currently **Python 3.11+**.
- `requirements.txt` is configured to use the PyTorch CUDA 12.4 wheel index.
- The ingest pipeline now requires **real sentence-transformer embeddings**; hash-placeholder embeddings are disabled.

For full setup, including Zotero, LoRA, and Anystyle:

- [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- [docs/WSL_LAUNCHER.md](docs/WSL_LAUNCHER.md)

## Core workflow

1. Configure `.env` with your OpenAI key and Zotero paths.
2. Start the stack with `make start` or `./scripts/run_ra_from_repo.sh start`.
3. Open the web UI and use `Sync + Ingest` for anti-join syncs, or `Zotero PDF Browser` to search available Zotero-backed PDFs and ingest or re-ingest selected items.
4. Use `Search` for paper or chunk retrieval.

## Zotero WebDAV fallback

If Zotero-managed attachments are not locally reachable from the runtime, you can configure WebDAV fallback in `.env`:

- `ZOTERO_WEBDAV_URL`
- `ZOTERO_WEBDAV_USERNAME`
- `ZOTERO_WEBDAV_PASSWORD`
- `ZOTERO_WEBDAV_CACHE_DIR`

Resolver order:

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
- `Import PDF URL To Stored Attachment` prompts for a PDF URL and imports it as a Zotero-managed stored attachment under the currently selected parent item.
- `Normalize Linked PDFs To Stored Attachments` converts selected linked PDF attachments into Zotero-managed stored attachments under the same parent item.

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

## Local conveniences

- Auto-versioning can be enabled locally with:

```bash
git config core.hooksPath .githooks
```

- Optional daily Dropbox sync helper:

```bash
scripts/rclone_sync_dropbox.sh
```
