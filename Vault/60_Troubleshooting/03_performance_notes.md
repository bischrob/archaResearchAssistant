# Performance and Scale Notes

## Heavy local data
- `\\192.168.0.37\pooled\media\Books\pdfs` contains ~4223 PDFs and ~25G.
- `db/` ~6.2G and `.cache/` ~1.3G.

## Ingest performance characteristics
- Parsing is per-file and CPU-bound (PyMuPDF extraction + chunking).
- Embedding generation is cheap hashing, not model inference, so fast but less semantic.
- `all` mode batches by `partial_count` in API layer for progress and survivability.

## Query performance characteristics
- Multi-channel retrieval calls several Cypher queries per request.
- Quality/rank speed depends on Neo4j index health and graph size.

## Sync performance characteristics
- `rclone` uses high parallel defaults (`transfers=16`, `checkers=32`).
- Remote counting (`rclone lsf`) can add overhead but improves progress estimates.

## Scalability limitations
- Single-process uvicorn with in-memory job manager.
- No distributed queue or worker pool.
- No persistent cache invalidation policy for `.cache/rag_articles`.

## Optimization candidates
1. Batch Neo4j writes in larger transactions.
2. Add adaptive retrieval limits by query complexity.
3. Add cache pruning and disk budget checks.
4. Move long jobs to durable task queue if concurrency needs grow.

## Recent experiments
- [[60_Troubleshooting/04_pdf_oxide_evaluation_2026-02-27]]: A/B benchmark of `pdf_oxide` vs PyMuPDF extraction (speed gains with text-equivalence risks).
- [[60_Troubleshooting/05_pdf_oxide_security_audit_2026-02-27]]: quick security review (OSV + supply-chain + code-path hardening checks).
