# archaResearch Assistant

archaResearch Assistant is a Zotero-first research ingestion and retrieval system with a Neo4j backend, FastAPI web service, web UI, and operator CLI.

The current recommended workflow is:

1. Configure the local environment and `.env`.
2. Start the stack with the repo wrapper or `ra` CLI.
3. Run Zotero-backed sync and ingest.
4. Use query and ask flows for retrieval and grounded synthesis.

Sync responses now also report MinerU note coverage so you can see how much of the Zotero attachment set is note-ingestible before or during ingest.

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

- Preferred local entrypoint: `ra`
- Linux repo wrapper: `./scripts/run_ra_from_repo.sh`
- PowerShell repo wrapper: `.\scripts\run_ra_from_repo.ps1`
- Installed CLI entrypoint: `ra`
- Default ingest mode: Zotero-backed sync (`source_mode=zotero_db`)
- Typical daily flow: `start`, `status`, `diagnostics`, `sync dry-run`, `sync ingest`, `query`, `ask`

## Quickstart

```bash
[ -d "$HOME/.conda/envs/researchassistant" ] || conda env create -f environment.yml
conda activate researchassistant
[ -f .env ] || cp .env.example .env
# edit .env and set the required values before continuing
pip install -e .
ra preflight
ra start
ra status
```

PowerShell equivalent:

```powershell
if (-not (conda env list | Select-String 'researchassistant')) { conda env create -f environment.yml }
conda activate researchassistant
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# edit .env and set the required values before continuing
pip install -e .
.\tasks.ps1 preflight
.\tasks.ps1 start
.\tasks.ps1 status
```

Direct wrapper equivalent:

```powershell
if (-not (conda env list | Select-String 'researchassistant')) { conda env create -f environment.yml }
conda activate researchassistant
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# edit .env and set the required values before continuing
pip install -e .
.\scripts\run_ra_from_repo.ps1 preflight
.\scripts\run_ra_from_repo.ps1 start
.\scripts\run_ra_from_repo.ps1 status
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

Use the repo wrapper when you want predictable local defaults, or call `ra` directly once the environment is active:

```bash
ra start
ra status
ra diagnostics
ra sync dry-run
ra sync ingest
ra query "community archives metadata"
ra ask "What are the main tradeoffs in AI-generated archival metadata?"
```

Useful sync output fields to watch:

- `zotero_mineru_notes_attached`
- `zotero_mineru_notes_missing`
- `zotero_mineru_notes_attached_for_ingest_candidates`
- `zotero_mineru_notes_missing_for_ingest_candidates`
- `zotero_mineru_notes_coverage_percent`

Useful item-level commands:

```bash
ra zotero-search "ethnography"
ra zotero-ingest PID1 PID2
ra article someCiteKey2026
```

## CLI Targets

There are two common API targets:

- Local repo-hosted service: `http://127.0.0.1:8001`
- `home2` service: `http://192.168.0.37:8001`

Rules of thumb:

- `ra` and the repo wrappers default to the local service unless you override `RA_BASE_URL`.
- After `ra start`, later repo-local `status` and `diagnostics` calls reuse the last local base URL that start selected.
- `status` is the quick health/version check; use `diagnostics` or `status --include-diagnostics` for the slower deep check.
- `ra` may default differently depending on environment, especially under WSL.
- Override either path with `RA_BASE_URL` or `--base-url` when needed.

Examples:

```bash
ra --json status
ra --base-url http://192.168.0.37:8001 status
ra --base-url http://127.0.0.1:8001 diagnostics
```

PowerShell repo wrapper examples:

```powershell
.\scripts\run_ra_from_repo.ps1 --json status
.\scripts\run_ra_from_repo.ps1 --base-url http://192.168.0.37:8001 status
```

PowerShell task runner examples:

```powershell
.\tasks.ps1 preflight
.\tasks.ps1 smoke
.\tasks.ps1 sync-example
```

## Web UI And Plugin

After startup, open the web GUI URL printed by `ra start`. The main workflow is:

1. Refresh health.
2. Run `Sync + Ingest` in Zotero DB mode.
3. Use search, article inspection, and ask flows after ingest completes.

The Zotero plugin scaffold lives in `plugins/zotero-rag-sync/` and supports the same sync-oriented workflow.

It also now includes a local Zotero connector bridge for outside note producers.
That bridge lets external scripts push MinerU-style markdown into Zotero as
structured child notes keyed by Zotero attachment key, which keeps the repo's
note-first ingest path compatible with batch OCR/markdown generation that
happens outside Zotero. See `plugins/zotero-rag-sync/README.md` and
`scripts/push_mineru_notes_via_zotero_bridge.py`.

To enable the bridge in Zotero, set both plugin prefs:

- `extensions.zotero-rag-sync.externalBridgeEnabled=true`
- `extensions.zotero-rag-sync.externalBridgeToken=<long random token>`

The local bridge endpoints are:

- `GET http://127.0.0.1:23119/rag-sync/bridge/ping`
- `POST http://127.0.0.1:23119/rag-sync/bridge/import-mineru-note`

The plugin package is built from:

- `plugins/zotero-rag-sync/manifest.json`
- `plugins/zotero-rag-sync/bootstrap.js`
- `plugins/zotero-rag-sync/prefs.js`
- `plugins/zotero-rag-sync/content/scripts/ragsync.js`

Build the `.xpi` with:

```bash
INSTALL_AFTER_BUILD=0 scripts/build_zotero_plugin_xpi.sh
```

Install the built plugin into the active Windows Zotero profile with:

```bash
SOURCE_XPI=/tmp/rag-sync@rjbischo.local.xpi scripts/install_zotero_plugin_windows.sh
```

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
- the shared repo reference parser in `src/rag/reference_parsing.py`

Overall process:

1. Detect the references section in markdown or OCR-derived text.
2. Split that section into one reference string per entry.
3. Parse each entry individually with deterministic heuristic parsing, confidence scoring, and optional bounded LLM repair in `hybrid_llm` or `llm` modes.
4. Build a structured `Citation` object with:
   - `raw_text`
   - `raw_text_original`
   - `title_guess`
   - `normalized_title`
   - `year`
   - `doi`
   - `author_tokens`
   - `authors`
   - `parse_method`
   - `parse_confidence`
   - `split_confidence`
   - `needs_review`
5. Score each parsed citation with a simple quality heuristic.
6. Reject clearly invalid entries such as DOI-only artifacts and mark low-confidence entries with `needs_review=true`.
7. Drop citations that fail the quality threshold before writing them to Neo4j.

When stored in Neo4j, each parsed citation becomes a `Reference` node linked from its source article by `(:Article)-[:CITES_REFERENCE]->(:Reference)`.

Supported parser modes:

- `CITATION_PARSER=heuristic`
- `CITATION_PARSER=hybrid_llm`
- `CITATION_PARSER=llm`

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
.\.venv\Scripts\python.exe -m pytest -m "not e2e"
```

Common shortcuts:

```bash
make test
make test-e2e
make smoke
```

Useful focused checks:

```bash
.\.venv\Scripts\python.exe -m pytest tests/test_zotero_notes.py tests/test_zotero_metadata.py tests/test_web_api.py -k zotero -q
```

## Project Layout

- `src/rag/`: application package and CLI implementation
- `scripts/`: operational scripts and maintenance utilities, including:
- `scripts/push_mineru_notes_via_zotero_bridge.py`
- `scripts/merge_author_nodes.py`
- `scripts/cleanup_isolated_authors.py`
- `webapp/`: FastAPI entrypoint and static UI
- `tests/`: automated tests
- `docs/`: setup and operator documentation
- `plugins/`: Zotero plugin scaffold

## Graph Maintenance

The graph now includes two small review-first maintenance helpers for author cleanup:

- `scripts/merge_author_nodes.py`
  - lists likely duplicate `Author` nodes with `candidates`
  - dry-runs a merge by default and only writes with `--apply`
- `scripts/cleanup_isolated_authors.py`
  - lists zero-edge `Author` nodes by default
  - deletes them only with `--apply`

Examples:

```bash
.\.venv\Scripts\python.exe scripts/merge_author_nodes.py --neo4j-password "$NEO4J_PASSWORD" candidates --min-score 0.85 --limit 20
.\.venv\Scripts\python.exe scripts/merge_author_nodes.py --neo4j-password "$NEO4J_PASSWORD" merge --source Brandsen --target "Alex Brandsen"
.\.venv\Scripts\python.exe scripts/cleanup_isolated_authors.py --neo4j-password "$NEO4J_PASSWORD"
```

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
