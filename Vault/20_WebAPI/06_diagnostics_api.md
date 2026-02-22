# Web API: Diagnostics Endpoint

## Source file
- `webapp/main.py` (`GET /api/diagnostics`)

## Purpose
Provide quick runtime health checks spanning config, data, and DB connectivity.

## Checks emitted
- `paperpile_json_exists`
- `sync_script_exists`
- `openai_api_key_set`
- `metadata_coverage_nonzero`
- `pdf_headers_sample_quality`
- `neo4j_connectivity`

## Additional detail payload
- local PDF totals
- metadata match counts
- unmatched sample list
- sampled PDF header quality
- Neo4j graph stats or error

## Pass/fail logic
Overall `ok` is true only if all checks have `ok=true`.

## Caveats
- Metadata coverage check only requires nonzero, not threshold quality.
- Header quality samples up to 300 files and uses `%PDF` prefix only.
- Connectivity check creates live `GraphStore`; credentials/network must be valid.

## Extension points
- Add disk usage checks.
- Add index existence/state checks.
- Add OpenAI key validation ping with opt-in.

## Related
- [[00_Project/03_runtime_and_config]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
