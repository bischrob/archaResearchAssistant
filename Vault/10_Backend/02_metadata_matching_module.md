# Backend Module: Paperpile Metadata Matching

## Source file
- `src/rag/paperpile_metadata.py`

## Responsibility
Load `Paperpile.json`, normalize attachment filenames, and resolve metadata for local PDFs.

## Key functions
- `load_paperpile_index(path)`: builds metadata index by exact basename and normalized key.
- `find_metadata_for_pdf(index, filename)`: exact lookup, then normalized fallback.
- `find_unmatched_pdfs(pdf_root, index)`: list PDFs without metadata match.

## Matching strategy
- Exact match on lowercase basename first.
- Fallback uses normalized filename key:
  - unicode decomposition (remove accents)
  - casefold
  - strip non-alphanumeric

## Metadata fields captured
- `title`, `year`, `citekey`, `paperpile_id`, `doi`, `journal`, `publisher`, `authors`.

## Failure modes
- Missing/invalid `Paperpile.json` returns empty index.
- Non-list JSON payloads are ignored (treated as empty).
- Attachment-less records contribute nothing.

## Operational impact
`choose_pdfs(... require_metadata=True)` and `ingest_pdfs` will skip files with no metadata.

## Extension points
- Add extra fields to `meta` dict.
- Adjust `_score` to choose best duplicate attachment record.
- Add diagnostics for per-field completeness.

## Related
- [[10_Backend/04_ingest_pipeline_module]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
