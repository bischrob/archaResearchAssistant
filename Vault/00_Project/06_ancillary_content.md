# Ancillary Content

## `drafts/computational_archaeology/`
- Contains Quarto book source (`*.qmd`, `_quarto.yml`, `references.bib`, theme).
- Includes rendered site output in `_book/`.
- Separate from runtime RAG backend, but shares research domain context.

## `pdf2epub/`
- Contains marker workflow artifacts:
  - `input/` sample PDFs
  - `output/` markdown + extracted images + metadata JSON
  - `Knappett.md`, `Knappett.epub`
- Has dedicated compose file (`pdf2epub/docker-compose.yml`).

## `anystyle/`
- Docker build context for `anystyle-cli` and `pdftotext`-based parsing experiments.
- Wired into a dedicated test ingest path via `scripts/build_graph_anystyle_test.py` (optional citation override path; default ingest remains unchanged).

## `research/`
- Directory exists but empty at review time.

## Interpretation
These folders suggest experimental or authoring workflows adjacent to the main production path. Treat them as optional subsystems unless explicitly integrated.

## Related
- [[00_Project/02_repository_map]]
- [[40_Scripts/03_docker_services]]
