# Troubleshooting Matrix

## `ModuleNotFoundError: No module named 'src'` when running tests
- Symptom: pytest collection errors across all test files.
- Cause: repo root not on `PYTHONPATH`.
- Fix: run `PYTHONPATH=. pytest -q` or configure pytest/pythonpath packaging.

## `/api/health` or ingest/query endpoints fail with DB errors
- Symptom: connection/auth exceptions.
- Cause: Neo4j container down, wrong credentials, wrong URI.
- Fix: run `docker compose up -d neo4j`; verify env values; run `scripts/init_neo4j_indexes.py`.

## Ingest reports no files selected
- Symptom: `No PDFs found to ingest` or metadata-related empty selection.
- Cause: strict filters (`skip_existing`, `require_metadata`) remove all candidates.
- Fix: check preview endpoint, set override existing, repair metadata mapping in `Paperpile.json`.

## Many PDFs skipped as failed
- Symptom: large `failed_pdfs` list.
- Cause: bad headers, unreadable PDFs, parse errors.
- Fix: run `scripts/delete_invalid_pdfs.sh --dry-run`; inspect first errors; test with single-file custom ingest.

## `/api/ask` returns key error
- Symptom: HTTP 400 with `OPENAI_API_KEY is not set`.
- Cause: missing env key.
- Fix: set `.env` or process env and restart app.

## `/api/ask` returns citation enforcement failure message
- Symptom: answer replaced with warning about missing `[C#]` citations.
- Cause: model output omitted citation IDs.
- Fix: retry with higher `rag_results`; refine question; temporarily disable enforce-citations for debugging.

## Sync fails immediately
- Symptom: sync job status `failed` with shell output.
- Cause: missing `rclone`, invalid `google.config`, remote path issues.
- Fix: run sync script directly from shell and verify `rclone` remote config.

## PDF export fails
- Symptom: `/api/ask/export` PDF returns 400.
- Cause: missing `pandoc` and/or PDF engine binary.
- Fix: install pandoc and at least one engine (`wkhtmltopdf`, `weasyprint`, `xelatex`, `pdflatex`).

## Zotero plugin "not installing"
- Symptom: plugin behavior missing and no plugin logs.
- Cause: Zotero session started in Safe Mode (`safeMode => true`), plugin copied to non-active profile, or manifest missing `applications.zotero.update_url` (reported as `Invalid XPI`).
- Fix: start Zotero in normal mode, verify active profile `extensions/rag-sync@rjbischo.local.xpi`, and ensure manifest includes `applications.zotero.update_url`.
- Details: [[60_Troubleshooting/06_zotero_plugin_install_not_visible_2026-03-18]]
