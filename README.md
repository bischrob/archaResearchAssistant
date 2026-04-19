# archaResearch Assistant

archaResearch Assistant is a Zotero-first research ingestion and retrieval system with a Neo4j backend, FastAPI web service, web UI, and operator CLI.

The current recommended workflow is:

1. Configure the local environment and `.env`.
2. Start the stack with the repo wrapper or `ra` CLI.
3. Run Zotero-backed sync and ingest.
4. Use query and ask flows for retrieval and grounded synthesis.

## Start Here

- Setup guide: [docs/NEW_USER_SETUP.md](docs/NEW_USER_SETUP.md)
- Operator runbook: [docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md)
- Documentation index: [docs/INDEX.md](docs/INDEX.md)
- Troubleshooting: [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Model setup: [docs/MODEL_SETUP.md](docs/MODEL_SETUP.md)
- Citation lookup guide: [docs/CITATION_LOOKUP.md](docs/CITATION_LOOKUP.md)
- WSL launcher notes: [docs/WSL_LAUNCHER.md](docs/WSL_LAUNCHER.md)

## What Changed

The repo now centers on the repo-native operator CLI instead of ad hoc curl calls and one-off helper scripts.

- Preferred local entrypoint: `./scripts/run_ra_from_repo.sh`
- Installed CLI entrypoint: `ra`
- Default ingest mode: Zotero-backed sync (`source_mode=zotero_db`)
- Typical daily flow: `start`, `status`, `diagnostics`, `sync dry-run`, `sync ingest`, `query`, `ask`

## Quickstart

```bash
conda env create -f environment.yml
conda activate researchassistant
cp .env.example .env
pip install -e .
make preflight
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
```

Minimum `.env` values:

- `OPENAI_API_KEY`
- `METADATA_BACKEND=zotero`
- `ZOTERO_REQUIRE_PERSISTENT_ID=1`
- `ZOTERO_DB_PATH`
- `ZOTERO_STORAGE_ROOT`

Optional but commonly used:

- `API_BEARER_TOKEN`
- `ZOTERO_WEBDAV_URL`
- `ZOTERO_WEBDAV_USERNAME`
- `ZOTERO_WEBDAV_PASSWORD`
- `ZOTERO_WEBDAV_CACHE_DIR`
- `QWEN3_MODEL_PATH`

## Daily Operator Flow

Use the repo wrapper when you want predictable local defaults:

```bash
./scripts/run_ra_from_repo.sh start
./scripts/run_ra_from_repo.sh status
./scripts/run_ra_from_repo.sh diagnostics
./scripts/run_ra_from_repo.sh sync dry-run
./scripts/run_ra_from_repo.sh sync ingest
./scripts/run_ra_from_repo.sh query "community archives metadata"
./scripts/run_ra_from_repo.sh ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Useful item-level commands:

```bash
./scripts/run_ra_from_repo.sh zotero-search "ethnography"
./scripts/run_ra_from_repo.sh zotero-ingest PID1 PID2
./scripts/run_ra_from_repo.sh article someCiteKey2026
```

## CLI Targets

There are two common API targets:

- Local repo-hosted service: `http://127.0.0.1:8001`
- `home2` service: `http://192.168.0.37:8001`

Rules of thumb:

- `./scripts/run_ra_from_repo.sh` defaults to the local service.
- `ra` may default differently depending on environment, especially under WSL.
- Override either path with `RA_BASE_URL` or `--base-url` when needed.

Examples:

```bash
./scripts/run_ra_from_repo.sh --json status
./scripts/run_ra_from_repo.sh --base-url http://192.168.0.37:8001 status
ra --base-url http://127.0.0.1:8001 diagnostics
```

## Web UI And Plugin

After startup, open the web GUI shown by `start.sh`. The main workflow is:

1. Refresh health.
2. Run `Sync + Ingest` in Zotero DB mode.
3. Use search, article inspection, and ask flows after ingest completes.

The Zotero plugin scaffold lives in `plugins/zotero-rag-sync/` and supports the same sync-oriented workflow.

## Reference Parsing

The current ingest flow is Zotero-first and note-driven.

1. Sync selects PDFs from Zotero metadata and attachment records.
2. Ingest loads the linked MinerU child note markdown for each attachment rather than re-parsing references directly from the PDF during the main path.
3. The markdown is split into body chunks by heading structure for retrieval.
4. One or more reference sections are detected in that markdown, including repeated bibliography blocks such as chapter-level reference sections in edited volumes.
5. Each detected reference block is split into one entry per reference, with continuation lines such as DOI-only lines merged back into the preceding entry.
6. Those entries are parsed into structured citation objects with confidence-aware parsing logic, and parse failures are recorded on the article for auditability.
7. Parsed citations are quality-filtered before the article, chunks, and references are written to Neo4j.

In practice, that means the canonical reference source for the supported ingest path is the structured markdown/note layer associated with the Zotero item, not a standalone manual reference-extraction step from raw PDFs. The parser is designed to handle both single bibliography tails and multiple chapter-level reference sections in the same note.

The active repo workflow is centered on the Zotero attachment plus MinerU note pipeline.

## Reference Matching

Reference matching in this repo happens in three separate layers, each using different resources and keys.

### 1. Metadata matching for the source article

Before reference-to-article matching even starts, the system has to decide which Zotero metadata record belongs to the PDF being ingested.

Resources used:

- Zotero attachment metadata from `zotero.sqlite`
- Zotero attachment paths and attachment identifiers
- local path hints from the resolved PDF file

Matching order for article metadata lookup:

1. normalized full attachment path
2. basename of the PDF filename
3. normalized basename fallback

Important identity fields stored on the `Article` node:

- `zotero_persistent_id`
- `zotero_item_key`
- `zotero_attachment_key`
- `doi`
- `title_year_key`
- normalized source path and normalized filename stem

The `title_year_key` is built as a diacritic-folded, lowercased alphanumeric title plus publication year, for example `some normalized title|2024`.

### 2. Parsing raw references into structured `Reference` nodes

Once the source article is identified, the ingest path extracts references from the attached MinerU markdown note or a generated `.references.txt` sidecar.

Resources used:

- MinerU child note markdown attached to the Zotero item
- OCR-derived `.references.txt` sidecars when needed
- Anystyle parsing output for individual reference strings

Overall process:

1. Detect the references section in markdown or OCR-derived text.
2. Split that section into one reference string per entry.
3. Parse each entry individually with resilient Anystyle-based parsing.
4. Build a structured `Citation` object with:
   - `raw_text`
   - `title_guess`
   - `normalized_title`
   - `year`
   - `doi`
   - `author_tokens`
   - `authors`
   - `bibtex`
5. Score each parsed citation with a simple quality heuristic.
6. Drop citations that fail the quality threshold before writing them to Neo4j.

When stored in Neo4j, each parsed citation becomes a `Reference` node linked from its source article by `(:Article)-[:CITES_REFERENCE]->(:Reference)`.

### 3. Resolving parsed references back to known articles

After articles and references are ingested, the graph layer tries to turn a parsed bibliography entry into an article-to-article citation edge.

Resources used:

- parsed reference DOI
- parsed reference normalized title
- parsed reference author tokens
- parsed reference year
- all ingested `Article` nodes already in the current batch

Primary resolution algorithm:

1. If the reference DOI exactly matches a target article DOI, the match is accepted immediately.
   Method recorded: `reference_doi_match`
2. Otherwise, compare the reference `normalized_title` to every candidate article `title_norm` using `difflib.SequenceMatcher`.
3. Compute author overlap from parsed `author_tokens` against the target article author-token set.
4. Treat the year as compatible if either side is missing or the years are within `+/-1`.
5. Score the candidate as:
   - `0.80 * title_score`
   - `0.15 * author_overlap`
   - `0.05` bonus for year compatibility
6. Accept the best candidate if one of these thresholds is met:
   - DOI exact match
   - score `>= 0.62`, title similarity `>= 0.55`, and year compatible
   - title similarity `>= 0.80`

If accepted, the repo creates:

- `(:Article)-[:CITES {match_score, method}]->(:Article)`
- `(:Reference)-[:RESOLVES_TO]->(:Article)` when the edge came from a specific parsed reference

### 4. Fallback citation-link heuristics

If structured reference matching does not produce a link, the graph layer still has two fallback heuristics for connecting articles inside the same ingest batch.

Fallback 1: in-text author-year mention

- scan the source article chunk text
- if the target article's primary author surname and publication year both appear in the text, create a `CITES` edge
- stored with method `in_text_author_year` and score `0.55`

Fallback 2: same-author prior-work heuristic

- if two articles share the same primary author surname
- and the source article is newer than the target article
- create a low-confidence `CITES` edge
- stored with method `same_author_prior_work` and score `0.35`

### 5. Matching existing graph records during Zotero reconciliation

Separately from bibliography matching, the repo also reconciles newly seen Zotero rows against already ingested `Article` nodes so it can attach missing Zotero IDs without full re-ingest.

Resources used:

- `zotero_item_key`
- `zotero_attachment_key`
- normalized DOI
- `title_year_key`

Reconciliation order:

1. `zotero_item_key`
2. `zotero_attachment_key`
3. DOI
4. `title_year_key`

Only unique matches are accepted. If a candidate key points to multiple existing articles, that case is marked ambiguous and skipped rather than guessed.

## Testing

Run the default non-e2e suite:

```bash
pytest -m "not e2e"
```

Common shortcuts:

```bash
make test
make test-e2e
make smoke
```

## Project Layout

- `src/rag/`: application package and CLI implementation
- `scripts/`: operational scripts and maintenance utilities
- `webapp/`: FastAPI entrypoint and static UI
- `tests/`: automated tests
- `docs/`: setup and operator documentation
- `plugins/`: Zotero plugin scaffold

## Included vs Excluded

Included in git:

- source code
- tests
- scripts
- docs
- plugin scaffold

Excluded from git:

- `.env`
- PDFs
- local models
- Neo4j runtime data
- logs
- Vault notes
- local debug artifacts

## Notes

- The supported local Python target is Python 3.11+ in the documented setup flow.
- Docker and Neo4j are required for the standard local stack.
- Use safe secret handling: keep API keys and tokens in `.env`, never in tracked files.
