# Zotero-first ingest implementation checklist (2026-03-21)

## Purpose
Translate the broader Zotero → Neo4j architecture into an implementation sequence for `researchAssistant`.

## Phase 1 — Make Zotero the authoritative ingest entrypoint

### 1.1 Add an explicit Zotero-first ingest mode
- [x] Add a new ingest mode centered on Zotero items/attachments rather than loose PDF discovery.
- [x] Treat filesystem-only ingest as legacy/backfill mode.
- [x] Require or strongly prefer `zotero_persistent_id` on `Article` during new ingest.

### 1.2 Define article identity contract
- [ ] Use `zotero_persistent_id = <libraryID>:<itemKey>` as the primary durable external identity.
- [ ] Keep support fields synchronized:
  - [ ] `zotero_item_key`
  - [ ] `zotero_attachment_key`
  - [ ] `zotero_library_id`
  - [ ] DOI/title/year fallback fields
- [ ] Decide whether Neo4j `Article.id` remains internal or is migrated to a Zotero-derived id scheme.

### 1.3 Tighten Zotero metadata sync
- [ ] Add a deterministic Zotero sync step before attachment/text ingest.
- [ ] Ensure author lists, year, title, DOI, collections/tags (if desired) are captured from Zotero.
- [ ] Record metadata provenance and last-sync version.

## Phase 2 — Attachment acquisition abstraction

### 2.1 Create a single attachment resolver
- [ ] Resolve attachment bytes or local file paths through one abstraction layer.
- [ ] Support:
  - [ ] local Zotero attachment paths
  - [ ] WebDAV-backed retrieval
  - [ ] cached local working copies
- [ ] Preserve provenance fields for every attachment fetch.

### 2.2 Add attachment-state diagnostics
- [ ] Missing attachment
- [ ] remote-only attachment
- [ ] local path broken
- [ ] WebDAV unavailable
- [ ] file hash / mtime / cache freshness

## Phase 3 — OCR/native text acquisition

### 3.1 Build formal text-acquisition decisioning
- [ ] Attempt native PDF text extraction first.
- [ ] Score text quality.
- [ ] Trigger PaddleOCR when text is missing or poor.
- [ ] Support `native_pdf`, `paddleocr`, and `hybrid` acquisition modes.

### 3.2 Preserve OCR provenance
- [ ] text source
- [ ] OCR engine/model version
- [ ] date processed
- [ ] confidence summary
- [ ] cached page text path

## Phase 4 — Section-aware document segmentation

### 4.1 Expand section model beyond main-text vs references
- [ ] `frontmatter`
- [ ] `body`
- [ ] `references` (one or more sections)
- [ ] `backmatter_other`

### 4.2 Improve layout-aware preprocessing
- [ ] remove repeated headers/footers/page numbers before semantic sectioning
- [ ] preserve heading candidates and page spans
- [ ] explicitly handle two-column PDFs where possible

### 4.3 Keep the LLM in the loop only for ambiguity
- [ ] classify uncertain boundaries
- [ ] distinguish references vs appendix/endnotes
- [ ] detect multiple reference sections in books/edited volumes
- [ ] avoid LLM usage for deterministic extraction/plumbing

## Phase 5 — Chunk model improvements

### 5.1 Enrich chunk metadata
- [ ] `section_type`
- [ ] `heading_path`
- [ ] `page_start`
- [ ] `page_end`
- [ ] raw text
- [ ] normalized text
- [ ] embedding
- [ ] token counts

### 5.2 Keep frontmatter separate from main retrieval content
- [ ] allow frontmatter chunking but label it separately
- [ ] make retrieval able to filter/down-rank frontmatter

### 5.3 Keep references separate from ordinary semantic chunks
- [ ] references should be exported as dedicated reference text artifacts
- [ ] optional audit/debug reference chunks can exist, but should not be treated like normal body chunks

## Phase 6 — `.references.txt` as a first-class artifact

### 6.1 Standardize reference-sidecar generation
- [ ] generate `<source-stem>.references.txt` for each recoverable reference section
- [ ] support multiple sidecars/section identifiers for books with multiple bibliographies if needed
- [ ] cache cleaned reference block and one-line reference output separately

### 6.2 Support manual cleanup workflow
- [ ] integrate the reference-line parser skill / equivalent process into ops workflow
- [ ] make manual cleanup an explicit supported stage, not an ad hoc exception
- [ ] preserve links between source text, cleaned sidecar, and parse results

## Phase 7 — Versioned reference ingest into Neo4j

### 7.1 Store corrected references with provenance
- [ ] raw cleaned one-line text
- [ ] parser output fields (Anystyle / BibTeX-like)
- [ ] parse method/version
- [ ] source section id
- [ ] source file/sidecar path
- [ ] created/updated timestamp
- [ ] corrected/manual flag

### 7.2 Introduce reference versioning / supersession model
- [ ] distinguish original extracted refs from manually corrected refs
- [ ] avoid silent overwrite of older reference states
- [ ] define one active reference set per article/section while preserving audit history

## Phase 8 — Resolution and graph derivation

### 8.1 Recompute article resolution from corrected refs
- [ ] DOI match
- [ ] title/year match
- [ ] author token overlap
- [ ] optional Zotero metadata-assisted matching

### 8.2 Maintain graph derivations
- [ ] `CITES_REFERENCE`
- [ ] `RESOLVES_TO`
- [ ] derived `CITES`
- [ ] cited-author links or equivalent derivation path

### 8.3 Separate raw ingest from derived-link recomputation
- [ ] keep reference writing and reference resolution as distinct stages/jobs
- [ ] allow safe re-resolution after correction without re-OCR/re-chunking the PDF

## Phase 9 — Author citation network

### 9.1 Expand author graph usefully
- [ ] ensure article authors are canonical enough for reuse
- [ ] attach cited-author identities to references where feasible
- [ ] decide whether author-author citation edges are materialized or computed dynamically

### 9.2 Retrieval signals from citation network
- [ ] same-author bias
- [ ] coauthor neighborhood bias
- [ ] cited/citing neighborhood bias
- [ ] journal/title/year exactness when relevant

## Phase 10 — Retrieval / RAG improvements

### 10.1 Keep hybrid retrieval as the base
- [ ] vector similarity over chunk embeddings
- [ ] token search over chunk text
- [ ] article-title / DOI / citekey exact retrieval

### 10.2 Add graph-aware re-ranking
- [ ] author proximity
- [ ] citation neighborhood proximity
- [ ] reference overlap
- [ ] section-aware chunk weighting

## Recommended implementation order
1. Zotero-first ingest mode + article identity cleanup
2. Attachment resolver (local Zotero path / WebDAV / cache)
3. OCR/native text acquisition stage
4. Section-aware segmentation
5. `.references.txt` sidecar generation
6. Versioned reference ingest
7. Reference resolution + `CITES` recomputation
8. Author-network-aware retrieval

## Immediate next milestone
Build a minimal end-to-end path for:
- Zotero item → attachment fetch → native/OCR text acquisition → section detection → body chunks + `.references.txt` → Anystyle parse → versioned `Reference` ingest

That milestone should be considered successful when one PDF-backed Zotero item can be ingested start-to-finish with:
- stable Zotero identity in Neo4j
- chunk embeddings stored
- cleaned reference sidecar produced
- parsed references stored with provenance
- safe re-run behavior without duplicate graph corruption
