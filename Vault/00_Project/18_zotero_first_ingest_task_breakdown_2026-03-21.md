# Zotero-first ingest task breakdown (2026-03-21)

## Purpose
Convert the Zotero-first ingest checklist into concrete implementation tasks for the current `researchAssistant` codebase.

## Milestone 1
**Get one Zotero item with a PDF attachment from Zotero/WebDAV all the way into Neo4j with:**
- stable Zotero identity on `Article`
- native/OCR text acquisition
- section-aware body/reference split
- body chunks embedded and stored
- cleaned `.references.txt` sidecar generated
- parsed `Reference` nodes written with provenance
- safe re-run behavior

---

## Epic A — Zotero-first ingest entrypoint

### Task A1 — Add Zotero-first ingest mode to settings and API
**Goal:** make Zotero item/attachment ingest a first-class mode.

**Status update (2026-03-21):** initial implementation completed. `choose_pdfs()` now accepts `source_mode`, defaults to `zotero_db`, and the ingest API/CLI path explicitly passes that mode. Filesystem ingest still exists, but is now the non-default path.

**Likely files:**
- `src/rag/config.py`
- `src/rag/pipeline.py`
- `webapp/main.py`
- `Vault/00_Project/03_runtime_and_config.md`
- `Vault/20_WebAPI/04_ingest_api.md`

**Changes:**
- add explicit ingest mode(s) such as:
  - `zotero_items`
  - `zotero_attachments`
- define required config for Zotero-backed ingest
- expose mode in API / job parameters

**Definition of done:**
- ingest job can be launched in Zotero-first mode without pretending PDFs are discovered from generic filesystem scan first

### Task A2 — Define article identity contract around Zotero persistent id
**Goal:** stop treating Zotero linkage as optional metadata for new ingest.

**Likely files:**
- `src/rag/metadata_provider.py`
- `src/rag/pipeline.py`
- `src/rag/neo4j_store.py`
- `scripts/backfill_zotero_identifiers.py`
- `Vault/60_Troubleshooting/09_zotero_identifier_backfill_2026-03-19.md`

**Changes:**
- decide whether `Article.id` remains internal or becomes Zotero-derived for new ingest
- require `zotero_persistent_id` on new Zotero-driven articles
- enforce stable source-path/provenance updates without breaking re-ingest matching

**Definition of done:**
- one Zotero item can be reingested repeatedly without creating duplicate `Article` nodes

---

## Epic B — Attachment resolver (local Zotero path / WebDAV / cache)

### Task B1 — Create a dedicated attachment resolution module
**Goal:** one place to get a PDF attachment for ingest.

**Status update (2026-03-21):** largely implemented. `src/rag/zotero_attachment_resolver.py` now acts as the shared acquisition layer and returns acquisition provenance distinguishing override/local storage/linked-path/WebDAV cache/WebDAV fetch/unresolved cases.

**Suggested new file:**
- `src/rag/zotero_attachment_resolver.py`

**Likely touched files:**
- `src/rag/pipeline.py`
- `src/rag/config.py`
- `docs/NEW_USER_SETUP.md`
- `Vault/00_Project/04_data_and_storage.md`

**Responsibilities:**
- resolve local Zotero attachment path when available
- resolve WebDAV-backed attachment when local path is unavailable
- create/use cached working copy
- return provenance record:
  - zotero item key
  - attachment key
  - library id
  - source mode (`local`, `webdav`, `cache`)
  - path/hash/mtime if applicable

**Definition of done:**
- ingest can request an attachment without caring whether it came from local Zotero storage or WebDAV

### Task B2 — Add attachment diagnostics and failure reporting
**Goal:** make attachment failures inspectable.

**Likely files:**
- `src/rag/pipeline.py`
- `webapp/main.py`
- `Vault/60_Troubleshooting/01_symptom_to_cause_matrix.md`

**Cases:**
- no PDF attachment
- WebDAV unavailable
- local attachment path missing
- attachment unreadable
- cache stale/corrupt

---

## Epic C — OCR/native text acquisition stage

### Task C1 — Introduce text-acquisition decision layer
**Goal:** formalize `native_pdf` vs `paddleocr` vs `hybrid`.

**Suggested new file:**
- `src/rag/text_acquisition.py`

**Likely touched files:**
- `src/rag/pdf_processing.py`
- `src/rag/pipeline.py`
- `src/rag/config.py`
- `Vault/10_Backend/03_pdf_processing_module.md`

**Responsibilities:**
- run native text extraction first
- score extraction quality
- trigger PaddleOCR when extraction is poor
- emit page-level text and acquisition provenance

**Definition of done:**
- scanned PDFs no longer silently fail into empty/garbage chunk sets if OCR is available

### Task C2 — Cache OCR/native outputs separately from article parse cache
**Goal:** make text acquisition auditable and reusable.

**Suggested cache areas:**
- `.cache/text_acquisition/...`
- `.cache/paddleocr/...`

**Definition of done:**
- OCR/native text can be rerun or audited independently of chunking/reference parsing

---

## Epic D — Section-aware segmentation

### Task D1 — Replace single references split with section model
**Goal:** move from `main text + references` to richer section typing.

**Suggested new file:**
- `src/rag/section_segmentation.py`

**Likely touched files:**
- `src/rag/pdf_processing.py`
- `src/rag/pipeline.py`
- `Vault/00_Project/14_section_chunk_detection_dataset_mvp_2026-03-19.md`
- `Vault/00_Project/15_qwen3_section_chunk_dataset_2026-03-19.md`
- `Vault/00_Project/16_section_chunk_heuristics_2026-03-19.md`

**Target section types:**
- `frontmatter`
- `body`
- `references`
- `backmatter_other`

**Definition of done:**
- parser can emit at least one `references` section and distinguish it from frontmatter/body for normal cases

### Task D2 — Support multiple reference sections
**Goal:** handle books/edited volumes.

**Definition of done:**
- pipeline can emit more than one references section per document with stable ordering/provenance

### Task D3 — Use LLM only for ambiguous section classification
**Goal:** keep human/LLM help where heuristics are weak.

**Likely files:**
- `src/rag/qwen_local.py`
- new classification helper or prompt module

**Definition of done:**
- deterministic heuristics run first; LLM only resolves hard boundary cases

**Status update (2026-03-21):** implemented in the current ingest path. Heuristics still propose heading/reference candidates, Qwen remains the ambiguity resolver via `detect_section_plan_with_qwen()`, and the resulting normalized section types now persist onto `Article`, `Chunk`, and `Section` graph metadata.

---

## Epic E — Chunk model enrichment

### Task E1 — Add richer chunk metadata
**Likely files:**
- `src/rag/pdf_processing.py`
- `src/rag/neo4j_store.py`
- `Vault/10_Backend/05_graph_store_module.md`

**Fields to add:**
- `section_type`
- `heading_path`
- `page_start`
- `page_end`
- normalized text if needed

**Definition of done:**
- retrieval and debugging can distinguish frontmatter/body chunks and trace chunks back to section context

### Task E2 — Keep references out of ordinary semantic body chunk retrieval
**Goal:** avoid bibliography noise dominating semantic search.

**Definition of done:**
- references are separately stored/exported while body retrieval remains clean

---

## Epic F — `.references.txt` sidecar generation

### Task F1 — Integrate sidecar generation into ingest
**Goal:** make cleaned references a first-class artifact.

**Likely files:**
- `src/rag/pipeline.py`
- `src/rag/anystyle_refs.py`
- `src/rag/section_segmentation.py` (new)
- maybe reuse `reference-line-parser` logic conceptually, but probably port into project code rather than invoking the OpenClaw skill directly

**Artifacts:**
- `<source-stem>.references.txt`
- optionally section-specific variants for multi-reference books

**Definition of done:**
- every recoverable references section yields an auditable one-reference-per-line text artifact before structured parsing

### Task F2 — Add manual review path for hard cases
**Goal:** make manual repair an intended workflow.

**Definition of done:**
- operator can replace/edit a sidecar and rerun only reference parsing/resolution without redoing OCR and chunk embedding

---

## Epic G — Versioned reference ingest

### Task G1 — Extend `Reference` schema with provenance/versioning
**Likely files:**
- `src/rag/neo4j_store.py`
- `scripts/neo4j_reference_roundtrip.py`
- `Vault/10_Backend/05_graph_store_module.md`

**Fields to add or formalize:**
- `source_section_id`
- `reference_source_path`
- `reference_import_method`
- `reference_version`
- `reference_status` (`raw`, `corrected`, `superseded`, etc.)
- parse method / parser version
- corrected/manual flags

**Definition of done:**
- corrected references do not silently destroy provenance of original extracted refs

### Task G2 — Safe overwrite / supersession model
**Goal:** allow corrected references to become active without losing audit history.

**Definition of done:**
- one article can have a new active reference set while old sets remain traceable

---

## Epic H — Resolution and derived citation graph

### Task H1 — Separate reference ingest from resolution
**Goal:** recompute graph links after correction without repeating upstream ingest.

**Suggested new file:**
- `src/rag/reference_resolution.py`

**Likely touched files:**
- `src/rag/neo4j_store.py`
- `scripts/apply_reference_corrections.py`

**Definition of done:**
- can rerun `Reference -> RESOLVES_TO -> CITES` logic independently of PDF parsing

### Task H2 — Add cited-author handling
**Goal:** support author citation network explicitly.

**Options:**
- materialize cited-author nodes/edges now
- or compute them dynamically from references + resolved articles

**Definition of done:**
- retrieval/ranking can use cited-author proximity as a signal

---

## Epic I — Retrieval optimization for citation/author neighborhoods

### Task I1 — Add graph-aware re-ranking signals
**Likely files:**
- `src/rag/retrieval.py`
- `src/rag/neo4j_store.py`
- `Vault/10_Backend/06_retrieval_module.md`

**Signals:**
- same-author boost
- coauthor neighborhood
- cited/citing neighborhood
- resolved-reference overlap
- section-aware chunk weighting

**Definition of done:**
- query results can favor same-author and citation-neighbor work in a controlled, inspectable way

---

## Suggested immediate work sequence

### Sprint 1
- A1, A2
- B1, B2
- C1

### Sprint 2
- C2
- D1, D2
- E1

### Sprint 3
- F1, F2
- G1, G2

### Sprint 4
- H1, H2
- I1

## First repo-level acceptance test
Use one Zotero item with a known PDF attachment and pass when all are true:
- article is ingested with stable Zotero identity
- attachment resolved through the new resolver
- native/OCR text provenance is stored
- body chunks exist with embeddings
- cleaned `.references.txt` sidecar exists
- parsed references exist in Neo4j with provenance/version metadata
- rerun does not duplicate article/chunk/reference state incorrectly

## Recommended first code targets
If starting immediately, touch these first:
1. `src/rag/config.py`
2. `src/rag/pipeline.py`
3. `src/rag/neo4j_store.py`
4. new `src/rag/zotero_attachment_resolver.py`
5. new `src/rag/text_acquisition.py`
6. new `src/rag/section_segmentation.py`
7. `webapp/main.py`
8. docs/Vault notes for runtime/config and ingest workflow
low


## Epic H — AI-driven keyword extraction

### Task H1 — Extract article-level retrieval keywords
**Status update (2026-03-21):** implemented. `src/rag/keyword_extraction.py` now derives an auditable keyword set from body chunks, prefers Qwen JSON output when available, and falls back to deterministic token-based extraction when not.

**Definition of done:**
- article ingest persists keywords plus extraction audit/provenance for later retrieval/reranking
