# Duplicate Detection Hardening (2026-03-18)

## Problem
- Duplicate detection missed some already-ingested papers when title text contained accents/diacritics.
- Custom 10-file ingest/sync runs could hang because custom mode still scanned the full default source root first.
- Zotero DB reads could fail while Zotero was open (`sqlite3.OperationalError: disk I/O error`).

## Code Changes
- `src/rag/metadata_provider.py`
  - `metadata_title_year_key()` now folds accents/diacritics (`NFKD`) before tokenization.
- `src/rag/neo4j_store.py`
  - `existing_article_identity_sets()` now also computes `title_year_key_normalized` from stored `title` + `year`, not only persisted `title_year_key`.
- `src/rag/pipeline.py`
  - `_is_existing_pdf()` now checks both `title_year_key` and `title_year_key_normalized`.
  - `choose_pdfs(mode='custom')` now bypasses global source scanning and only resolves explicit paths.
- `src/rag/zotero_metadata.py`
  - DB connect now prefers `mode=ro&immutable=1`, with fallback to `mode=ro`.

## Validation
- Test: `PYTHONPATH=. pytest -q tests/test_metadata_provider.py` passed.
- Added regression assertion for accented titles in `tests/test_metadata_provider.py`.

## New 10-file Sync Run
- Run mode: targeted custom ingest pipeline run with explicit Zotero DB/storage env vars.
- Input set size: 10 (different deterministic slice than previous run).
- Result:
  - `ingested_articles`: 10
  - `skipped_existing_pdfs`: 0
  - `skipped_no_metadata_pdfs`: 0
  - `failed_pdfs`: 0
- One non-fatal parser warning occurred during processing:
  - `MuPDF error: format error: No common ancestor in structure tree`
  - Ingest still completed successfully.

## Follow-up
- Restart backend with `ZOTERO_DB_PATH` and `ZOTERO_STORAGE_ROOT` set so `/api/ingest` and `/api/sync` use Zotero metadata consistently without manual env overrides.

## Related
- [[10_Backend/02_metadata_matching_module]]
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
- [[60_Troubleshooting/06_zotero_plugin_install_not_visible_2026-03-18]]
