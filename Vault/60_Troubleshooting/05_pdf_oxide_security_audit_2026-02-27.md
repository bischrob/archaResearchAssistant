# pdf_oxide Security Audit (2026-02-27)

## Scope
Quick security review of `pdf_oxide` `0.3.9` for this pipeline, focused on:
- known vulnerabilities
- dependency/supply-chain posture
- code-level hardening signals relevant to untrusted PDF parsing

## Evidence collected
- Installed wheel metadata and SBOM:
  - `/home/rjbischo/miniconda3/lib/python3.12/site-packages/pdf_oxide-0.3.9.dist-info/METADATA`
  - `/home/rjbischo/miniconda3/lib/python3.12/site-packages/pdf_oxide-0.3.9.dist-info/sboms/pdf_oxide.cyclonedx.json`
- OSV scan report:
  - `logs/pdf_oxide_osv_scan_2026-02-27.json`
- Upstream repo snapshot:
  - `/tmp/pdf_oxide_audit_20260227`

## Findings

### 1) `lzw 0.10.0` advisory in shipped dependency graph (Medium)
- OSV hit from SBOM scan: `RUSTSEC-2020-0144` (`lzw` unmaintained).
- `lzw = "0.10.0"` is declared directly in `Cargo.toml`.
- Code paths appear to use `weezl` + custom decoder, not the external `lzw` crate.
- Impact: no known RCE/CVE-style exploit attached to this advisory, but unmaintained parser dependencies are a long-term risk for untrusted input.
- Recommendation: remove direct `lzw` dependency if unused (or replace with maintained path only).

### 2) Decompression-bomb guard exists but main stream decode path bypasses it (Medium)
- `decode_stream_with_options` includes ratio/size checks in `src/decoders/mod.rs`.
- Main object decode path in `src/object.rs` calls `decode_stream_with_params` (no ratio/size checks).
- Impact: potential memory pressure/exhaustion risk on crafted compressed streams.
- Recommendation: route stream decoding through guarded path by default (or enforce equivalent checks in `decode_stream_with_params`).

### 3) Parser limit knobs are present but not clearly wired/exposed end-to-end (Low/Medium)
- `ParserOptions` includes `max_file_size`, `max_nesting`, and `max_recursion_depth` fields in `src/parser_config.rs`.
- `PdfDocument` stores `options` with `#[allow(dead_code)]` and there is no visible public `open_with_options(...)` path.
- Impact: security docs recommend configurable limits, but current API surface may not enforce all claimed controls for Python consumers.
- Recommendation: expose parser options via public APIs and verify each limit is actively enforced in parse/stream paths.

### 4) Supply-chain posture: generally good, with a few trust gaps (Low)
- Positive:
  - no Python runtime dependencies (`Requires-Dist: None`)
  - wheel includes CycloneDX SBOM
  - CI includes dependency audit (`cargo audit`, `cargo-deny`) and Dependabot config exists
  - no public GitHub security advisories were returned at audit time
- Gaps:
  - PyPI release inspected had wheels only (no sdist in `0.3.9`)
  - PyPI file metadata shows `has_sig: false`
  - release publishing workflow uses `PYPI_API_TOKEN` (not Trusted Publishing OIDC flow)

## Overall quick verdict
- **Not blocked** for controlled internal evaluation.
- For production parsing of untrusted PDFs, treat current risk as **moderate** until:
  1. `lzw` advisory is eliminated (remove unused dependency),
  2. decompression limits are enforced in the primary decode path,
  3. parser limits are clearly wired and configurable from public API.

## Related
- [[60_Troubleshooting/04_pdf_oxide_evaluation_2026-02-27]]
- [[10_Backend/03_pdf_processing_module]]
