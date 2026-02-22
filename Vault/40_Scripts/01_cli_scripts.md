# CLI Scripts (Python)

## Source files
- `scripts/build_graph.py`
- `scripts/build_graph_anystyle_test.py`
- `scripts/query_graph.py`
- `scripts/init_neo4j_indexes.py`
- `scripts/find_pdfs_missing_metadata.py`

## `build_graph.py`
- Purpose: choose + ingest PDFs from CLI.
- Inputs: mode, pdf-dir, partial-count, explicit `--pdf`, `--override-existing`.
- Uses `choose_pdfs` and `ingest_pdfs`.

## `build_graph_anystyle_test.py`
- Purpose: run test ingest that attempts citation extraction via Anystyle in Docker before ingest.
- Inputs: ingest mode args plus `--anystyle-service`, `--anystyle-timeout`, `--require-anystyle`.
- Behavior: applies per-article citation overrides only when Anystyle returns references; otherwise falls back to built-in parser.
- Re-ingest behavior is duplicate-safe for per-article references because existing reference/citation edges are refreshed before write.

## `query_graph.py`
- Purpose: run contextual retrieval from CLI.
- Inputs: query string, limit.
- Prints ranked results with chunk excerpt and citation neighborhood.

## `init_neo4j_indexes.py`
- Purpose: wait for Neo4j, create schema, list indexes/constraints.
- Inputs: wait/retry parameters.
- Useful for startup and troubleshooting schema state.

## `find_pdfs_missing_metadata.py`
- Purpose: detect PDFs without Paperpile attachment metadata match.
- Outputs: CSV with filename and paths.

## Shared behavior
Each script prepends repo root to `sys.path` to allow `src.*` imports without package install.

## Related
- [[10_Backend/04_ingest_pipeline_module]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
