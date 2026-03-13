# Backend Module: Retrieval and Reranking

## Source file
- `src/rag/retrieval.py`

## Responsibility
Parse user query and produce top contextual chunks (or top papers) via hybrid multi-channel retrieval + reranking.

## Stages
1. Parse query into:
   - content tokens
   - years
   - quoted phrases
   - author-like terms
   - must-terms (uppercase/proper-noun-like hints)
2. Pull candidates from store channels:
   - vector
   - token
   - author
   - title
3. Merge by `chunk_id` and accumulate `combined_score`.
4. Rerank with lexical overlaps + year/phrase + graph-neighborhood bonus.
5. Optionally enforce must-term filtering.
6. Low-confidence fallback: force-merge author hits and rerank.
7. Optional paper aggregation mode:
   - group reranked chunks by article identity
   - compute `paper_score` from top chunk quality + top-2 average + retrieval-source diversity
   - return one row per paper with `highlight_chunks`

## Scoring features
- semantic signals: vector, token, author, title channel contributions.
- lexical signals: chunk/title/author token overlap.
- explicit match signals: year and phrase.
- graph signal: cite neighborhood degree bonus.

## Output
- `limit_scope="chunks"`: list of chunk rows with scores, retrieval source list, and query feature diagnostics.
- `limit_scope="papers"`: list of paper rows with:
  - article metadata
  - top-chunk preview fields (for UI compatibility)
  - `paper_score`, `paper_chunk_count`, `paper_retrieval_sources`
  - `highlight_chunks` (up to `chunks_per_paper`)

## Failure modes
- Empty tokens leads to pass-through top-k without rerank feature strength.
- Over-filtering via must-terms can hide relevant hits if query capitalization is noisy.

## Extension points
- Add query intent classifier for mode-specific weighting.
- Learn weights from relevance feedback.
- Add citedness/time-decay controls for recency balancing.

## Related
- [[20_WebAPI/05_query_and_ask_api]]
- [[70_Feature_Playbooks/02_add_retrieval_signal]]
