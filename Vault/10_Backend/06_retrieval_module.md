# Backend Module: Retrieval and Reranking

## Source file
- `src/rag/retrieval.py`

## Responsibility
Parse user query and produce top contextual chunks via hybrid multi-channel retrieval + reranking.

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

## Scoring features
- semantic signals: vector, token, author, title channel contributions.
- lexical signals: chunk/title/author token overlap.
- explicit match signals: year and phrase.
- graph signal: cite neighborhood degree bonus.

## Output
List of chunk rows with scores, retrieval source list, and query feature diagnostics.

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
