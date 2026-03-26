# Operator Runbook

This is the preferred daily operator path for archaResearch Assistant.

## Start and verify

```bash
python scripts/ra.py start
python scripts/ra.py status
python scripts/ra.py diagnostics
```

Notes:
- The default ra target is the home2 service at http://192.168.0.37:8001. Use --base-url or RA_BASE_URL to point elsewhere.
- `ra start` reuses `./start.sh` and writes a background log under `logs/`.
- `ra status` checks `/api/version`, `/api/health`, `/api/diagnostics`, and async job status endpoints.

## Zotero-first ingest

Preview what still needs work:

```bash
python scripts/ra.py sync dry-run
```

Run the anti-join sync plus ingest:

```bash
python scripts/ra.py sync ingest
```

Search Zotero-backed available PDFs:

```bash
python scripts/ra.py zotero-search "ethnography"
```

Ingest one or more specific Zotero persistent IDs:

```bash
python scripts/ra.py zotero-ingest PID1 PID2
```

## Retrieval and synthesis

Discovery query:

```bash
python scripts/ra.py query "community archives metadata"
```

Grounded answer synthesis:

```bash
python scripts/ra.py ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Inspect a known paper:

```bash
ra article wiseEvaluationAIgeneratedMetadata2026
ra articles wiseEvaluationAIgeneratedMetadata2026 shawThinkingFastSlowArtificial2026
```

## Troubleshooting

- If `ra start` fails early, inspect the referenced `logs/ra-start-*.log` file.
- If `ra status` says the API is unreachable, verify Docker/Neo4j first and then retry `ra start`.
- If Zotero search or sync fails, re-check `.env` values for `ZOTERO_DB_PATH`, `ZOTERO_STORAGE_ROOT`, and optional WebDAV settings.
- For deeper diagnosis, use `python scripts/ra.py diagnostics` and `docs/TROUBLESHOOTING.md`.
UBLESHOOTING.md`.
ostics`) and `docs/TROUBLESHOOTING.md`.
e `python scripts/ra.py diagnostics` and `docs/TROUBLESHOOTING.md`.
