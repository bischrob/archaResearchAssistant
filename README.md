# archaResearch Assistant

archaResearch Assistant is a Zotero-first research ingestion and retrieval system with a Neo4j backend, FastAPI web service, web UI, and operator CLI.

The current recommended workflow is:

1. Configure the local environment and `.env`.
2. Start the stack with the repo wrapper or `ra` CLI.
3. Run Zotero-backed sync and ingest.
4. Use query and ask flows for retrieval and grounded synthesis.

## Start Here

- Setup guide: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Operator runbook: [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md)
- Documentation index: [docs/INDEX.md](docs/INDEX.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Citation lookup guide: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- WSL launcher notes: [docs/WSL_LAUNCHER.md](docs/WSL_LAUNCHER.md)

## What Changed

The repo now centers on the repo-native operator CLI instead of ad hoc curl calls and one-off helper scripts.

- Preferred local entrypoint: `./scripts/run_ra_from_repo.sh`
- Installed CLI entrypoint: `ra`
- Default ingest mode: Zotero-backed sync (`source_mode=zotero_db`)
- Typical daily flow: `start`, `status`, `diagnostics`, `sync dry-run`, `sync ingest`, `query`, `ask`

## Quickstart

```bash
conda env create -f environment.yml
conda activate researchassistant
cp .env.example .env
pip install -e .
make preflight
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
```

Minimum `.env` values:

- `OPENAI_API_KEY`
- `METADATA_BACKEND=zotero`
- `ZOTERO_REQUIRE_PERSISTENT_ID=1`
- `ZOTERO_DB_PATH`
- `ZOTERO_STORAGE_ROOT`

Optional but commonly used:

- `API_BEARER_TOKEN`
- `ZOTERO_WEBDAV_URL`
- `ZOTERO_WEBDAV_USERNAME`
- `ZOTERO_WEBDAV_PASSWORD`
- `ZOTERO_WEBDAV_CACHE_DIR`
- `QWEN3_MODEL_PATH`

## Daily Operator Flow

Use the repo wrapper when you want predictable local defaults:

```bash
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
./scripts/run_ra_from_repo.sh diagnostics
./scripts/run_ra_from_repo.sh sync dry-run
./scripts/run_ra_from_repo.sh sync ingest
./scripts/run_ra_from_repo.sh query "community archives metadata"
./scripts/run_ra_from_repo.sh ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Useful item-level commands:

```bash
./scripts/run_ra_from_repo.sh zotero-search "ethnography"
./scripts/run_ra_from_repo.sh zotero-ingest PID1 PID2
./scripts/run_ra_from_repo.sh article someCiteKey2026
```

## CLI Targets

There are two common API targets:

- Local repo-hosted service: `http://127.0.0.1:8001`
- `home2` service: `http://192.168.0.37:8001`

Rules of thumb:

- `./scripts/run_ra_from_repo.sh` defaults to the local service.
- `ra` may default differently depending on environment, especially under WSL.
- Override either path with `RA_BASE_URL` or `--base-url` when needed.

Examples:

```bash
./scripts/run_ra_from_repo.sh --json status
./scripts/run_ra_from_repo.sh --base-url http://192.168.0.37:8001 status
ra --base-url http://127.0.0.1:8001 diagnostics
```

## Web UI And Plugin

After startup, open the web GUI shown by `start.sh`. The main workflow is:

1. Refresh health.
2. Run `Sync + Ingest` in Zotero DB mode.
3. Use search, article inspection, and ask flows after ingest completes.

The Zotero plugin scaffold lives in `plugins/zotero-rag-sync/` and supports the same sync-oriented workflow.

## Testing

Run the default non-e2e suite:

```bash
pytest -m "not e2e"
```

Common shortcuts:

```bash
make test
make test-e2e
make smoke
```

## Project Layout

- `src/rag/`: application package and CLI implementation
- `scripts/`: operational scripts and maintenance utilities
- `webapp/`: FastAPI entrypoint and static UI
- `tests/`: automated tests
- `docs/`: setup and operator documentation
- `plugins/`: Zotero plugin scaffold

## Included vs Excluded

Included in git:

- source code
- tests
- scripts
- docs
- plugin scaffold

Excluded from git:

- `.env`
- PDFs
- local models
- Neo4j runtime data
- logs
- Vault notes
- local debug artifacts

## Notes

- The supported local Python target is Python 3.11+ in the documented setup flow.
- Docker and Neo4j are required for the standard local stack.
- Use safe secret handling: keep API keys and tokens in `.env`, never in tracked files.
