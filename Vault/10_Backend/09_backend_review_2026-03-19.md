# Backend Review (2026-03-19)

## Focus
Review of ingest pipeline, metadata matching, dedupe identities, graph write safety, and cancellation behavior.

## Key findings
### Blocker
1. Graph refresh path is not transaction-safe for delete/rebuild sequences.
- Risk: cancel/failure can leave partial article graph state.
- Affected area: `src/rag/neo4j_store.py` ingest and refresh logic.

### High
1. Citation linking can crash on null author paths (`.lower()` on `None`).
2. If selected articles have zero chunks, ingest path can return early and skip expected writes.
3. Re-ingest may keep stale author edges (`WROTE`) from prior versions.
4. Dedupe fallback to filename stem can false-match unrelated files with same stem.
5. Metadata lookup precedence can choose basename match before safer path match.
6. Zotero attachment query may include `storage:*` entries that are not true PDFs.

### Medium
1. UNC fallback path resolution can fabricate mount-like paths after failed mount attempts.
2. ZIP PDF extraction lacks strong limits for member size/count (resource risk).

## Review action package
### M0
1. Define atomic ingest refresh strategy
- Acceptance: failure/cancel never leaves article chunk/reference graph partially deleted.
- Regression tests: cancel mid-refresh and failure injection state checks.

### M1
1. Null-safe citation linking and author normalization
- Acceptance: no null-author crashes.
- Tests: citation linker with missing author fields.

2. Dedupe correctness hardening
- Acceptance: identity precedence is deterministic (doi -> zotero keys -> title/year -> stem fallback).
- Tests: matrix for duplicate stems, DOI normalization, and key collisions.

3. Metadata match disambiguation
- Acceptance: path-aware match wins for duplicate basenames when path hint is present.
- Tests: same filename in distinct folders.

4. Zotero attachment filtering precision
- Acceptance: non-PDF artifacts do not enter ingest candidate set.
- Tests: attachment query fixtures with mixed content types/paths.

### M2
1. ZIP and UNC safety controls
- Acceptance: extraction/resource limits enforced and path fallback behavior explicit.
- Tests: large ZIP/member count guards; mount failure path behavior.

## Verification scenarios
1. Run targeted ingest with forced cancellation during article refresh and validate graph consistency.
2. Replay a known duplicate-stem dataset and confirm dedupe decisions remain correct.
3. Ingest from Zotero DB fixture containing mixed attachment types and confirm PDF-only selection.

## Owner
- Backend data path owner (pipeline + graph store)

## Related
- [[10_Backend/02_metadata_matching_module]]
- [[10_Backend/04_ingest_pipeline_module]]
- [[10_Backend/05_graph_store_module]]
- [[60_Troubleshooting/08_codebase_workflow_review_2026-03-19]]
