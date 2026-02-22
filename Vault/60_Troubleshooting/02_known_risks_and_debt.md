# Known Risks and Technical Debt

## Config/model mismatch
- `EMBEDDING_MODEL` is configurable but currently unused by `GraphStore` (hashing embedder only).

## Test ergonomics
- Test suite needs explicit `PYTHONPATH=.` in current setup.

## Sync cancellation test mismatch
- One test failing because fake process does not match real stream assumptions.

## Heuristic citation linking
- `CITES` inference uses title similarity + fallback heuristics; false positives possible.

## LLM API integration style
- Uses raw `requests` to `/v1/chat/completions` without structured outputs; rewrite parsing may be brittle.

## Frontend rendering approach
- Manual markdown-to-HTML implementation may miss edge cases compared to mature parser.

## File anomalies
- `activateSol.sh` appears corrupted/non-text.
- `anystyle/Dockerfile` may include malformed apt line continuation.

## State durability
- Job manager state is in-memory only; no persistent task history.

## Security posture
- Defaults include hardcoded Neo4j password in config/compose examples.
- Broad CORS policy (`allow_origins=["*"]`).

## Repository state note at review time
- Working tree was already dirty before vault creation (`src/rag/neo4j_store.py`, `webapp/main.py` modified).
- Preserve these local changes when debugging unless intentionally discarded by maintainer.
