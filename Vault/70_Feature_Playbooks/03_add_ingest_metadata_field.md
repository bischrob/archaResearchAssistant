# Playbook: Add a New Ingest Metadata Field

## Goal
Add metadata from `Paperpile.json` through ingest and retrieval paths.

## Touch points
- `src/rag/paperpile_metadata.py`: extract and store field in `meta`.
- `src/rag/pdf_processing.py`: include field on `ArticleDoc` if needed.
- `src/rag/neo4j_store.py`: write field to `Article` node.
- Query/output paths: include field in retrieval returns as needed.
- API/UI: display field in preview and result tables if relevant.

## Steps
1. Add field extraction and normalization.
2. Thread field through dataclasses and persistence writes.
3. Update lookup/query return projections.
4. Add tests for extraction and endpoint visibility.

## Guardrails
- Keep backward compatibility for old cached article payloads.
- Avoid breaking deserialize path in `pipeline._deserialize_article`.

## Validation checklist
- Metadata appears in ingest preview and stored graph nodes.
- Existing ingestion still works for records missing the new field.
