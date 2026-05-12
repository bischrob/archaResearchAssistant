# Operator Runbook

This is the preferred daily operator path for archaResearch Assistant.

## Pick the target first

There are two common API targets:

- **local repo-hosted service**: `http://127.0.0.1:8001`
- **home2 service**: `http://192.168.0.37:8001`

Recommended rule:

- use `ra ...` when the environment is already active
- use the direct repo wrapper when you want predictable local defaults from a shell script:
  - Linux: `./scripts/run_ra_from_repo.sh ...`
  - PowerShell: `.\scripts\run_ra_from_repo.ps1 ...`
- use `.\tasks.ps1 ...` on Windows when you want a PowerShell-native equivalent to the Linux `Makefile`
- use the installed `ra` launcher when you want convenience, but remember that on WSL it defaults to `home2`
- override with `RA_BASE_URL` or `--base-url` whenever the default is not the service you intend

Examples:

```bash
ra --json status
ra --base-url http://192.168.0.37:8001 --json status
ra --base-url http://127.0.0.1:8001 --json status
```

```powershell
.\tasks.ps1 preflight
.\tasks.ps1 start
.\tasks.ps1 status
.\tasks.ps1 smoke
```

## Start and verify

Local repo-hosted start:

```bash
ra start
ra status
ra diagnostics
```

If you prefer the launcher but want the local service explicitly:

```bash
ra --base-url http://127.0.0.1:8001 start
ra --base-url http://127.0.0.1:8001 status
ra --base-url http://127.0.0.1:8001 diagnostics
```

Notes:

- `ra start` now performs startup orchestration in Python and writes a background log under `logs/`.
- after `ra start` chooses an open local port, later repo-local status checks reuse that last selected local base URL unless you override it
- `ra status` checks `/api/version`, `/api/health`, and async job status endpoints.
- use `ra diagnostics` or `ra status --include-diagnostics` when you want the slower deep environment scan
- `ra diagnostics` is the quickest sanity check for source-mode and Zotero resolver state.

## Zotero-first ingest

Preview what still needs work:

```bash
ra sync dry-run
```

Run the anti-join sync plus ingest:

```bash
ra sync ingest
```

MinerU coverage is now included in sync results. The most useful fields are:

- `zotero_mineru_notes_attached`
- `zotero_mineru_notes_missing`
- `zotero_mineru_notes_attached_for_ingest_candidates`
- `zotero_mineru_notes_missing_for_ingest_candidates`
- `zotero_mineru_notes_coverage_percent`

Search Zotero-backed available PDFs:

```bash
ra zotero-search "ethnography"
```

Ingest one or more specific Zotero persistent IDs:

```bash
ra zotero-ingest PID1 PID2
```

## Retrieval and synthesis

Discovery query:

```bash
ra query "community archives metadata"
```

Grounded answer synthesis:

```bash
ra ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Inspect known papers:

```bash
ra article wiseEvaluationAIgeneratedMetadata2026
ra articles wiseEvaluationAIgeneratedMetadata2026 shawThinkingFastSlowArtificial2026
```

## Troubleshooting

- If `ra start` fails early, inspect the referenced `logs/ra-start-*.log` file.
- If `ra status` says the API is unreachable, confirm you are talking to the intended target before debugging the service.
- If Zotero search or sync fails, re-check `.env` values for `ZOTERO_DB_PATH`, `ZOTERO_STORAGE_ROOT`, and optional WebDAV settings.
- For deeper diagnosis, use `ra diagnostics` and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).
