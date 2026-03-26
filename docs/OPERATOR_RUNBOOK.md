# Operator Runbook

This is the preferred daily operator path for archaResearch Assistant.

## Pick the target first

There are two common API targets:

- **local repo-hosted service**: `http://127.0.0.1:8001`
- **home2 service**: `http://192.168.0.37:8001`

Recommended rule:

- use the direct repo wrapper (`./scripts/run_ra_from_repo.sh ...`) when you want predictable local defaults
- use the installed `ra` launcher when you want convenience, but remember that on WSL it defaults to `home2`
- override with `RA_BASE_URL` or `--base-url` whenever the default is not the service you intend

Examples:

```bash
./scripts/run_ra_from_repo.sh --json status
./scripts/run_ra_from_repo.sh --base-url http://192.168.0.37:8001 --json status
ra --base-url http://127.0.0.1:8001 --json status
```

## Start and verify

Local repo-hosted start:

```bash
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
./scripts/run_ra_from_repo.sh diagnostics
```

If you prefer the launcher but want the local service explicitly:

```bash
ra --base-url http://127.0.0.1:8001 start
ra --base-url http://127.0.0.1:8001 status
ra --base-url http://127.0.0.1:8001 diagnostics
```

Notes:

- `ra start` reuses `./start.sh` and writes a background log under `logs/`.
- `ra status` checks `/api/version`, `/api/health`, `/api/diagnostics`, and async job status endpoints.
- `ra diagnostics` is the quickest sanity check for source-mode and Zotero resolver state.

## Zotero-first ingest

Preview what still needs work:

```bash
./scripts/run_ra_from_repo.sh sync dry-run
```

Run the anti-join sync plus ingest:

```bash
./scripts/run_ra_from_repo.sh sync ingest
```

Search Zotero-backed available PDFs:

```bash
./scripts/run_ra_from_repo.sh zotero-search "ethnography"
```

Ingest one or more specific Zotero persistent IDs:

```bash
./scripts/run_ra_from_repo.sh zotero-ingest PID1 PID2
```

## Retrieval and synthesis

Discovery query:

```bash
./scripts/run_ra_from_repo.sh query "community archives metadata"
```

Grounded answer synthesis:

```bash
./scripts/run_ra_from_repo.sh ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Inspect known papers:

```bash
./scripts/run_ra_from_repo.sh article wiseEvaluationAIgeneratedMetadata2026
./scripts/run_ra_from_repo.sh articles wiseEvaluationAIgeneratedMetadata2026 shawThinkingFastSlowArtificial2026
```

## Troubleshooting

- If `ra start` fails early, inspect the referenced `logs/ra-start-*.log` file.
- If `ra status` says the API is unreachable, confirm you are talking to the intended target before debugging the service.
- If Zotero search or sync fails, re-check `.env` values for `ZOTERO_DB_PATH`, `ZOTERO_STORAGE_ROOT`, and optional WebDAV settings.
- For deeper diagnosis, use `./scripts/run_ra_from_repo.sh diagnostics` and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
