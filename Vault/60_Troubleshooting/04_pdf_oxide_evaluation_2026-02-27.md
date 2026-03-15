# pdf_oxide Evaluation (2026-02-27)

## Goal
Check whether replacing current PyMuPDF (`fitz`) text extraction with `pdf_oxide` improves ingest pipeline performance without harming extraction quality.

## Upstream package checked
- Repo: https://github.com/yfedoseev/pdf_oxide
- API used: `PdfDocument(...).page_count()`, `PdfDocument(...).extract_text(page_index)`

## Test setup
- Environment date: 2026-02-27
- Current extractor in code: `src/rag/pdf_processing.py` (`_extract_page_text` via `fitz`)
- `pdf_oxide` installed: `0.3.9`
- Comparison mode: same PDFs, alternating run order per file to reduce warm-cache bias.

### Run A: Full `load_article` A/B on 20 ingest-selected PDFs
- Report file: `logs/pdf_oxide_benchmark_2026-02-27.json`
- Selection: `choose_pdfs(mode=\"batch\", require_metadata=True, partial_count=20, skip_existing=False)`
- Key results:
  - Runtime: `fitz 14.05s` vs `pdf_oxide 2.75s` (~`5.1x` faster total)
  - Per-file winner: `pdf_oxide` faster on `19/20` files
  - Extracted chars: `+1.13%` (`pdf_oxide` vs `fitz`)
  - Chunk words: `-0.38%`
  - Heuristic citations: `-53.9%` (significant regression for built-in reference parsing path)

### Run B: Extraction-only sweep on 100 ingest-selected PDFs
- Report file: `logs/pdf_oxide_extract_sweep_100_2026-02-27.json`
- Key results:
  - Runtime: `fitz 20.83s` vs `pdf_oxide 5.21s` (~`4.0x` faster total)
  - Per-file winner: `pdf_oxide` faster on `98/100` files
  - No hard parse failures on either extractor (`0/100` failures each)
  - Token-vocabulary similarity to current output:
    - median recall (`pdf_oxide` tokens vs `fitz` tokens): `0.959`
    - docs with recall `< 0.9`: `22/100`
    - docs with recall `< 0.8`: `5/100`
    - docs with Jaccard `< 0.8`: `25/100`

## Notable quality risk observed
- One sample (`\\192.168.0.37\pooled\media\Books\pdfs\-(pdf)SpeciousArtOfSingle-cellGenomics.pdf`) produced visibly garbled `pdf_oxide` text (character substitutions/merged text), with very low token recall against current output (`0.164`).
- This indicates a non-trivial risk of retrieval quality regression on a subset of PDFs if switched globally.

## Conclusion
- `pdf_oxide` is consistently and substantially faster.
- Output is not consistently equivalent to current `fitz` extraction; some PDFs show major textual divergence.
- Global one-step replacement is not yet recommended for this pipeline.

## Recommended integration strategy
1. Add `PDF_EXTRACTOR` setting (`fitz|pdf_oxide|auto`), default `fitz`.
2. Implement `auto` mode:
   - try `pdf_oxide` first for speed
   - run lightweight quality checks (text length floor, suspicious character ratio, section-heading plausibility)
   - fallback to `fitz` when checks fail
3. Re-run retrieval-level validation on a fixed question set before defaulting to `auto`.

## Related
- [[10_Backend/03_pdf_processing_module]]
- [[60_Troubleshooting/03_performance_notes]]
- [[60_Troubleshooting/05_pdf_oxide_security_audit_2026-02-27]]
