# API + Plugin Review (2026-03-19)

## Focus
Review of `/api/sync|ingest` contracts, status/stop semantics, auth consistency, and Zotero plugin sync state machine.

## Key findings
### Blocker
1. Plugin timeout/background path can clear local running state while backend sync is still running.
- Risk: duplicate starts and false idle diagnostics.

### High
1. `/api/sync` contract has drifted from static web frontend expectations (`returncode/stdout/stderr` vs structured sync payload).
2. Stop endpoints return 200 with ambiguous semantics (cancel accepted vs no-op vs already terminal).
3. Auth policy is inconsistent across job endpoints (sync/ingest enforced optionally, query/preview less consistent).
4. Web static client lacks bearer-token support, so secured API mode can break web controls while plugin still works.
5. Job lifecycle state is in-memory and single-slot, with no retained history across restarts.

### Medium
1. Overlay background mode removes immediate cancel affordance after dismissal.
2. Cancellation payload semantics differ between sync and ingest, increasing client complexity.
3. Observability gaps: no structured lifecycle logs, no per-job history, no explicit cancelling state.

## Review action package
### M0
1. Plugin state-machine correctness
- Acceptance: if backend status is `running`, plugin local status cannot regress to idle.
- Regression tests: timeout path, background mode, terminal state transitions.

### M1
1. API contract unification
- Acceptance: sync/ingest status/stop payloads follow common shape and cancel semantics.
- Tests: contract tests for success, cancel accepted, cancel no-op, and failure.

2. Client compatibility alignment
- Acceptance: static web UI and plugin both parse current API payloads correctly.
- Tests: frontend parser tests and end-to-end sync/ingest UI smoke tests.

3. Auth consistency policy
- Acceptance: documented and enforced policy across sync/ingest/query/status/stop/preview.
- Tests: endpoint auth matrix with and without `API_BEARER_TOKEN`.

### M2
1. Lifecycle observability
- Acceptance: structured job logs include request IDs, transitions, durations, terminal reasons.
- Tests: status and log assertions in integration tests.

## Expected status model (target)
`idle -> running -> {completed | failed | cancelled}`

Optional explicit transitional state:
`running -> cancelling -> cancelled`

## Owner
- Web API + plugin integration owner

## Related
- [[20_WebAPI/02_job_manager]]
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
- [[60_Troubleshooting/08_codebase_workflow_review_2026-03-19]]
