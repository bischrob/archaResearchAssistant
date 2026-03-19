# Test Reliability Review (2026-03-19)

## Focus
Review of current test validity, harness stability, workflow coverage gaps, and flakiness in async lifecycle tests.

## Key findings
### High
1. Pipeline test suite has stale expectations and outdated monkeypatch targets relative to current ingest implementation.
2. Multiple ingest tests still assume old Paperpile-default behavior despite current Zotero-default runtime path.
3. Sync test coverage misses critical branches (`zotero_db` flow, run-ingest path, zero-PDF terminal path, auth matrix).
4. Dedupe logic has insufficient direct unit coverage for identity precedence and normalization paths.

### Medium
1. Plugin lifecycle behavior is effectively untested (poll timeout, background continuation, terminal state summaries).
2. Async API tests rely on timing windows and permissive assertions that can mask race conditions.
3. Test command contract remains fragile (`pytest` import path behavior requires explicit setup).

## Test matrix (target)
| Workflow | Priority scenarios |
|---|---|
| Sync | `filesystem` and `zotero_db` source modes, missing source errors, `run_ingest=true`, cancel during scan/ingest, concurrent start (`409`) |
| Ingest | mode mapping, metadata strictness on/off, parser required-success flags, mid-batch cancel, partial summary integrity |
| Dedupe | DOI/key/title-year/stem precedence, normalization edge cases, duplicate stem cross-directory behavior |
| API lifecycle | deterministic transition checks for `idle/running/completed/failed/cancelled`, stop semantics |
| Plugin | timeout/background continuation, cancel propagation, success/failure summary rendering |

## Review action package
### M1
1. Repair stale pipeline tests and align fixtures with current metadata backend behavior.
- Acceptance: maintained ingest/pipeline tests represent actual runtime defaults and pass consistently.

2. Add sync/ingest lifecycle coverage for missing high-risk branches.
- Acceptance: branch-level coverage includes source modes, cancel paths, run-ingest, and auth behavior.

3. Add direct dedupe unit tests.
- Acceptance: identity precedence and normalization decisions are deterministic and validated.

### M2
1. Harden async test determinism.
- Acceptance: reduced timing-flaky patterns and stricter state assertions.

2. Add plugin JS tests for state machine behavior.
- Acceptance: timeout/background/cancel terminal paths are covered.

## Status
- 2026-03-19: Added tests for sync source modes, run-ingest coverage, zero-PDF terminal completion, stop/cancel lifecycle assertions, bearer-token matrix checks, and dedupe precedence.
- 2026-03-19: Stabilized pytest invocation with repo-root import path and explicit importlib import mode.
- 2026-03-19: No production code changed in this pass; plugin JS lifecycle harness remains a follow-up.

## Owner
- Test architecture owner (API/backend integration + workflow regression suite)

## Related
- [[50_Testing/01_test_overview]]
- [[50_Testing/02_current_test_status_2026-02-21]]
- [[20_WebAPI/03_sync_api]]
- [[10_Backend/04_ingest_pipeline_module]]
- [[60_Troubleshooting/08_codebase_workflow_review_2026-03-19]]
