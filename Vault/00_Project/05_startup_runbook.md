# Startup Runbook

Last reviewed: 2026-03-19

## Standard startup
1. Start database service:
   - `docker compose up -d neo4j`
2. Or run one-step launcher:
   - `./start.sh`

## What `start.sh` does
- Validates Docker and compose availability.
- Ensures Docker daemon is running.
- Starts `neo4j` container if needed.
- Runs `python scripts/init_neo4j_indexes.py` unless `INIT_NEO4J_SCHEMA=0`.
- Launches web server via `scripts/run_web_gui.sh` (uvicorn, no reload by default).
- Auto-picks next open port if `PORT` is busy (prints selected URL).

## Manual API path (minimal checks)
1. Confirm UI/API is up:
   - `curl http://127.0.0.1:8000/`
2. Confirm job endpoints are responsive:
   - `curl http://127.0.0.1:8000/api/sync/status`
   - `curl http://127.0.0.1:8000/api/ingest/status`
3. Confirm known-paper lookup path:
   - `curl "http://127.0.0.1:8000/api/article/<citekey>?chunk_limit=1"`

## Startup prerequisites
- Python environment with `requirements.txt` installed.
- Docker daemon available.
- Neo4j port mapping available (`7474`, `7687`).
- Optional for LLM: `OPENAI_API_KEY`.
- Optional for PDF report export: `pandoc` + PDF engine.

## Common startup failures
- Docker missing/not running.
- Neo4j connection timeout during schema init.
- Missing dependency when launching uvicorn.
- API appears up but `/api/health` is slow/timeouts under heavy startup load; verify with `/`, `/api/sync/status`, and `/api/ingest/status`.

## Related notes
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
- [[20_WebAPI/09_citation_lookup_quickstart]]
- [[40_Scripts/01_cli_scripts]]
