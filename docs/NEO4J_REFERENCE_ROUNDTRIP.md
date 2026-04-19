# Neo4j reference round-trip from stored chunks

Minimal tooling to test whether chunk text already stored in Neo4j can drive the manual reference-cleanup workflow and then be written back into Neo4j.

## What it does

`scripts/sync_reference_roundtrip.py` supports two subcommands:

- `export`: fetch one article's chunk text from Neo4j, guess where the reference section starts, and write:
  - `<article>.article.json`
  - `<article>.chunks.references.json`
  - `<article>.references.block.txt`
  - `<article>.references.draft.txt`
- `import`: read a cleaned one-reference-per-line text file and write `Reference` nodes plus `(:Article)-[:CITES_REFERENCE]->(:Reference)` edges back into Neo4j.

To avoid clobbering a live article during evaluation, `import` can target a separate demo article id with `--article-id-out`.

## Export example

```bash
python scripts/sync_reference_roundtrip.py export abbott2007-BallcourtsCeramics-CaseHohokamMarketplacesInArizonaDesert
```

## Import example

Dry run only:

```bash
python scripts/sync_reference_roundtrip.py import \
  abbott2007-BallcourtsCeramics-CaseHohokamMarketplacesInArizonaDesert \
  tmp/reference_roundtrip/abbott2007-BallcourtsCeramics-CaseHohokamMarketplacesInArizonaDesert.references.draft.txt \
  --article-id-out abbott2007-BallcourtsCeramics-CaseHohokamMarketplacesInArizonaDesert::manual-demo \
  --dry-run
```

## Caveats

- This is evaluation tooling, not a broad ingest refactor.
- Chunk text quality determines everything. If the reference section never made it into chunks, export will not recover it.
- The script adds a few provenance-ish properties (`reference_import_method`, `reference_source_path`, `reference_demo_of`) but the main graph schema still does not model reference versions cleanly.
- `CITES` edges are not recomputed by this script. It writes `Reference` nodes and `CITES_REFERENCE` links only.
