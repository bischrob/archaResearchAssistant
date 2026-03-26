# Backend Module: Graph Store (Neo4j)

## Source file
- `src/rag/neo4j_store.py`

## Responsibility
Encapsulate schema setup, ingestion writes, and retrieval queries against Neo4j.

## Schema objects
- Node labels: `Article`, `Author`, `Chunk`, `Token`, `Reference`, `Section`, `Keyword`.
- Relationships: `WROTE`, `IN_ARTICLE`, `MENTIONS`, `CITES_REFERENCE`, `CITES`, `RESOLVES_TO`, `HAS_SECTION`, `HAS_KEYWORD`.
- Indexes/constraints include vector index `chunk_embedding`, fulltext for chunk/author/article, and text/uniqueness support for section and keyword metadata.

## Embedding model behavior
- Uses `SentenceTransformerEmbedder` for real semantic embeddings.
- Honors `embedding_model` and related embedding env vars.
- Fails hard if sentence-transformers is unavailable or a hash-placeholder configuration is requested.

## Ingestion responsibilities
- Upsert article metadata.
- Upsert authors and author order (`WROTE.position`).
- Upsert chunks with embeddings and section metadata (`section_type`, `section_id`, `section_label`).
- Upsert section spans as first-class `Section` nodes linked to the article.
- Upsert keyword nodes/relationships with extraction score/source/evidence plus article-level audit fields.
- Upsert token mention counts per chunk.
- Refresh per-article `Reference`/`CITES` edges before re-write to prevent stale duplicates on re-ingest.
- Upsert references (including optional DOI/source/author token metadata) and link citing article.
- Post-pass to infer `Article -> CITES -> Article` links using DOI/title/author/year composite matching plus fallbacks.

## Retrieval query APIs
- `token_query`, `vector_query`, `author_query`, `title_query`.
- `graph_stats`, `existing_article_ids`.
- citekey lookup helpers: `article_by_citekey`, `articles_by_citekeys`.

## Failure modes
- Cypher/query failures if indexes unavailable or db version mismatch.
- Inferred citation links may produce false positives due heuristic thresholds.
- Embedding approach is lexical-hash, not semantic SOTA embeddings.
- Citation linking still depends on overlap quality inside the current ingest batch.

## Extension points
- Swap `HashingEmbedder` with real sentence encoder.
- Add transaction batching for faster large ingestion.
- Separate citation-link inference into dedicated post-processing job.

## Related
- [[10_Backend/06_retrieval_module]]
- [[40_Scripts/01_cli_scripts]]
