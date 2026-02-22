# Startup Runbook

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
- Launches web server via `scripts/run_web_gui.sh` (uvicorn with reload).

## Manual CLI path
- Ingest: `python scripts/build_graph.py --mode batch --pdf-dir pdfs`
- Query: `python scripts/query_graph.py "<query>" --limit 5`

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

## Related notes
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
- [[40_Scripts/01_cli_scripts]]
