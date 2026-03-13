# Shell Scripts (Ops)

## Source files
- `start.sh`
- `scripts/run_web_gui.sh`
- `scripts/sync_pdfs_from_gdrive.sh`
- `scripts/delete_invalid_pdfs.sh`
- `backup_neo4j.sh`

## `start.sh`
- Ensures Docker + compose availability.
- Starts `neo4j` container if needed.
- Runs schema init script.
- Auto-selects an open web port (starting from `PORT` or `8000`) and exports it.
- Launches uvicorn script.

## `scripts/run_web_gui.sh`
- Starts FastAPI via `python -m uvicorn webapp.main:app --reload`.

## `scripts/sync_pdfs_from_gdrive.sh`
- Uses `rclone copy` from remote to local `pdfs/`.
- Non-destructive flags (`--ignore-existing`).
- Supports `--dry-run`.
- Reads optional OAuth fields from `google.config`.

## `scripts/delete_invalid_pdfs.sh`
- Scans PDFs and marks invalid if missing `%PDF` header or unreadable by `fitz`.
- Supports `--dry-run` and `--root`.

## `backup_neo4j.sh`
- Stops Neo4j, runs `neo4j-admin database dump`, then restarts.
- Includes commented restore command.

## Notable anomaly
`activateSol.sh` exists but appears binary/corrupted (`file` reports `data`). Treat as non-functional until repaired.

## Related
- [[00_Project/05_startup_runbook]]
- [[60_Troubleshooting/02_known_risks_and_debt]]
