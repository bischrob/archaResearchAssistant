# Archive: 2026-03-19 Process Cleanup

Purpose:
- Store legacy or non-runtime root files outside the active working set.
- Keep project root focused on current API/Zotero ingest workflow.

Scope:
- Historical export artifacts
- Legacy data-analysis outputs
- One-off docs/spreadsheets not required for current runtime path

Restore:
- Move any file back to project root if a legacy workflow needs it.
- Example:
  - `mv archive/2026-03-19_process_cleanup/index.cypher .`

Notes:
- Runtime/code/config directories were intentionally not moved.
- This archive commit is separated from functional/docs commits for cleaner review.
