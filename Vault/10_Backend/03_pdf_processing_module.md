# Backend Module: PDF Processing

## Source file
- `src/rag/pdf_processing.py`

## Responsibility
Parse one PDF into an `ArticleDoc` with text chunks, token counts, and extracted references.

## Pipeline
1. Parse fallback metadata from filename (`AuthorYYYY-Title` convention).
2. Extract text per page using PyMuPDF (`fitz`).
3. Optionally strip repeated page-edge noise (headers/footers/page numbers) before line assembly.
4. Split lines into main text and references section by heading match.
5. Chunk main text by word windows with overlap.
6. Tokenize chunk text and build token frequency maps.
7. Parse reference blocks into `Citation` records.

## Important heuristics
- Reference heading regex: `references|bibliography|works cited|literature cited`.
- Citation block starts when line looks like author + year at line start.
- Title guess extracted from text following year token.
- Repeated edge lines across pages are treated as header/footer noise and removed when enabled.
- Standalone page-number lines (arabic/roman) are removed when enabled.

## Data structures produced
- `Chunk` with page range and `token_counts`.
- `Citation` with raw text, year, guessed title, normalized title, optional DOI/author tokens/source.
- `ArticleDoc` with metadata + all chunks/citations.

## Failure modes
- Unreadable PDF throws upstream; caller records failed PDF.
- No chunk output may occur for mostly image/scanned PDFs with no text extraction.
- Heuristic reference extraction can mis-segment citations.

## Extension points
- Replace simple heading detection with layout-aware segmentation.
- Add OCR fallback for scanned/image PDFs.
- Improve citation parsing using dedicated parser service.
- Tune page-noise stripping thresholds per corpus (`CHUNK_STRIP_PAGE_NOISE`).

## Related
- [[10_Backend/04_ingest_pipeline_module]]
- [[40_Scripts/02_shell_scripts]] (invalid PDF cleanup)
