# Repository Map

## Main source directories
- `src/rag/`: backend domain logic (ingest, retrieval, LLM, export).
- `webapp/`: FastAPI app and static frontend.
- `scripts/`: CLI utilities for ingest/query/schema/metadata checks.
- `tests/`: pytest test suite.

## Data-heavy directories
- `\\192.168.0.37\pooled\media\Books\pdfs` (~25G, ~4223 PDFs): local corpus.
- `db/` (~6.2G): Neo4j volume mounts.
- `embeddings/` (~4.1G): local artifacts.
- `.cache/` (~1.3G): parse caches under `.cache/rag_articles/`.

## Other project content
- `drafts/computational_archaeology/`: Quarto book content and rendered HTML.
- `pdf2epub/`: marker-based PDF-to-markdown/epub experimentation.
- `anystyle/`: Docker image definition for reference parsing experiments.

## Top-level files of interest
- `README.md`: user-facing run instructions.
- `docker-compose.yml`: Neo4j + admin + anystyle services.
- `start.sh`: boot Neo4j, init schema, run web UI.
- `requirements.txt`: Python dependencies.
- `Paperpile.json`: large metadata source.

## Non-source large artifacts (selected)
- `upload.pkl` (~953M)
- `chunks_df.pkl` (~944M)
- `Paperpile.json` (~17M)

## Related notes
- [[00_Project/04_data_and_storage]]
- [[40_Scripts/03_docker_services]]
