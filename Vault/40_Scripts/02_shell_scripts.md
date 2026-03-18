# Shell Scripts (Ops)

## Source files
- `start.sh`
- `scripts/run_web_gui.sh`
- `scripts/sync_pdfs_from_gdrive.sh`
- `scripts/delete_invalid_pdfs.sh`
- `scripts/build_zotero_plugin_xpi.sh`
- `scripts/install_zotero_plugin_windows.sh`
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
- Uses `rclone copy` from remote to local `\\192.168.0.37\pooled\media\Books\pdfs`.
- Non-destructive flags (`--ignore-existing`).
- Supports `--dry-run`.
- Reads optional OAuth fields from `google.config`.

## `scripts/delete_invalid_pdfs.sh`
- Scans PDFs and marks invalid if missing `%PDF` header or unreadable by `fitz`.
- Supports `--dry-run` and `--root`.

## `scripts/build_zotero_plugin_xpi.sh`
- Builds `plugins/zotero-rag-sync` into `/tmp/rag-sync@rjbischo.local.xpi`.
- Enforces an allowlisted file set and checks `manifest.json` plus JS syntax with `node --check`.
- Verifies the archive contents after creation.
- By default also replaces the active Zotero profile extension XPI via `scripts/install_zotero_plugin_windows.sh` (`INSTALL_AFTER_BUILD=1`).
- Set `INSTALL_AFTER_BUILD=0` to build only.

## `scripts/install_zotero_plugin_windows.sh`
- Locates the active Zotero profile on Windows from `profiles.ini` or explicit overrides.
- Supports WSL installs by scanning `/mnt/<drive>/Users/*/AppData/Roaming/Zotero/Zotero` when env-based paths are unavailable.
- Supports explicit overrides via `ZOTERO_PROFILE_DIR` or `ZOTERO_PROFILE_BASE`.
- Backs up an existing `extensions/rag-sync@rjbischo.local.xpi` before replacing it.
- Removes the obsolete `extensions/rag-sync@local.xpi` file if it exists.

## `backup_neo4j.sh`
- Stops Neo4j, runs `neo4j-admin database dump`, then restarts.
- Includes commented restore command.

## Notable anomaly
`activateSol.sh` exists but appears binary/corrupted (`file` reports `data`). Treat as non-functional until repaired.

## Related
- [[00_Project/05_startup_runbook]]
- [[60_Troubleshooting/02_known_risks_and_debt]]
