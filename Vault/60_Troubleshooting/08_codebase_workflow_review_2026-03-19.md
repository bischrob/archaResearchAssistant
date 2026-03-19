# Codebase + Workflow Review (2026-03-19)

## Executive summary
This review consolidates backend, API/plugin, ops/workflow, and test-system findings into a single action package focused on reliability and correctness.

Highest-risk themes:
- ingest graph write safety and cancellation integrity
- sync/API lifecycle contract drift across clients
- operational reproducibility gaps (startup/training/backups)
- stale or broken tests masking real regressions

## Review baseline
Scope reviewed:
- Runtime and architecture docs: `README.md`, Vault project/runbook/troubleshooting/testing notes.
- Backend path: metadata/dedupe/ingest/graph write flow under `src/rag/`.
- API + clients: `webapp/main.py`, `webapp/static/app.js`, `plugins/zotero-rag-sync`.
- Ops/workflow scripts: startup, docker, backup, sync, SOL training scripts.
- Test system: `tests/*`, `pytest.ini`, test execution behavior.

## Source-of-truth drift table (documented vs actual)
| Area | Documented | Actual | Risk | Action |
|---|---|---|---|---|
| Sync API behavior | Vault `20_WebAPI/03_sync_api.md` still describes script stdout/stderr sync flow | `webapp/main.py` now runs metadata scan + optional ingest in-process | Medium | Update API docs and UI contract notes |
| Web UI sync result fields | Static frontend expects `returncode/stdout/stderr` | `/api/sync` returns structured sync summary payload | Critical | Align web UI to current API contract |
| Default citation parser | Vault notes imply default `anystyle` | runtime default is `qwen_refsplit_anystyle` | High | Update runtime/config docs and scripts docs |
| Test execution command | historical note says `PYTHONPATH=.` workaround required | still true; plain `pytest` import-collection fails | High | Fix harness config and update test runbook |
| Plugin timeout semantics | user expectation: long sync keeps status context | timeout path can still set local idle while backend runs | Critical | Fix plugin state machine timeout path |

## Top risks by severity
### Blocker
1. Non-transactional delete/rebuild graph writes can leave partial data on failure/cancel.
Owner: Backend

2. Plugin timeout/background state can mark sync idle while backend is still running.
Owner: Plugin + API lifecycle

### High
1. Null-author crash path in citation linking (`.lower()` on `None`) can fail ingest after partial writes.
Owner: Backend

2. `/api/sync` contract drift vs static web client expectations causes misleading UX and hidden error context.
Owner: Web UI + API

3. Stop semantics are ambiguous (`/stop` returns 200 with no clear cancel acceptance/no-op distinction).
Owner: API

4. Test suite reliability is degraded by stale ingest tests and harness import fragility.
Owner: Testing

5. SOL training scripts risk shared-env races and reproducibility drift.
Owner: Ops/Workflow

## Action plan by milestone
### M0 (Blockers)
1. Backend ingest write safety hardening
- Change intent: atomic or safer staged graph writes for article refresh path; explicit cancellation consistency.
- Acceptance criteria: cancel/failure cannot leave partially deleted article chunk/reference graph.
- Regression tests: mid-ingest cancel/failure integrity tests against graph state.
- Rollout checkpoint: run migration-safe ingest test set on representative PDFs.

2. Plugin/API lifecycle correctness
- Change intent: background timeout should keep accurate running state and prevent duplicate starts.
- Acceptance criteria: if backend status is running, plugin remains in running state until terminal confirmation.
- Regression tests: plugin poll-timeout integration tests; API status lifecycle assertions.
- Rollout checkpoint: manual end-to-end run with timeout window and diagnostics verification.

### M1 (High)
1. Null-safety and dedupe correctness in backend
- Change intent: guard null author paths, verify dedupe identity precedence and fallback behavior.
- Acceptance criteria: no null-author crashes; dedupe decisions stable under metadata/key edge cases.
- Regression tests: `_is_existing_pdf` precedence matrix and citation-link null cases.
- Rollout checkpoint: targeted ingest replay of known edge PDFs.

2. API/web contract alignment
- Change intent: unify response handling and status/stop semantics across sync/ingest/query.
- Acceptance criteria: all clients interpret sync/ingest statuses consistently.
- Regression tests: API contract tests for terminal/cancel/no-op states, frontend parser tests.
- Rollout checkpoint: UI sync run with success/failure/cancel states.

3. Testing system recovery
- Change intent: fix stale pipeline tests and stable import execution.
- Acceptance criteria: canonical pytest command is documented and green for maintained suites.
- Regression tests: refreshed ingest/sync/dedupe coverage including concurrency and cancellation.
- Rollout checkpoint: CI/local test baseline update.

4. Ops reliability and reproducibility
- Change intent: lock training env setup, improve startup/backup safety, and standardize provenance capture.
- Acceptance criteria: concurrent training jobs do not race env writes; backup cannot leave Neo4j down.
- Regression tests: script smoke tests for lock/trap/restart paths.
- Rollout checkpoint: dry run on SOL and local startup/backup validation.

### M2 (Medium)
1. Observability and docs parity
- Change intent: structured job lifecycle logging and Vault/README parity checks.
- Acceptance criteria: documented defaults and contracts match runtime.
- Regression tests: docs drift checks in review checklist.
- Rollout checkpoint: review sign-off checklist completed.

## Dependency chains
- API contract drift -> static web false error rendering -> operator confusion and bad triage.
- Plugin timeout state divergence -> duplicate sync submissions -> wasted runs and unclear status.
- Stale tests -> false confidence in ingest/dedupe behavior -> higher production regression risk.
- Ops env drift -> irreproducible model/training runs -> difficult rollback/comparison.

## Review completion checklist
- [ ] Every Blocker/High item has owner, acceptance criteria, and regression tests defined.
- [ ] API/plugin lifecycle expectations specify concrete status transitions.
- [ ] Dedupe/ingest items include reproducible failure-mode checks.
- [ ] Ops items include startup, backup, sync, and SOL reproducibility checks.
- [ ] Vault index links resolve to all review notes with no orphaned files.

## Sign-off criteria
- M0 plans are approved by backend + API/plugin owners.
- M1 scope is prioritized and sequenced with test-first gates.
- Updated docs remove current source-of-truth drift.

## Related
- [[10_Backend/09_backend_review_2026-03-19]]
- [[20_WebAPI/07_api_plugin_review_2026-03-19]]
- [[40_Scripts/04_ops_workflow_review_2026-03-19]]
- [[50_Testing/03_test_reliability_review_2026-03-19]]
- [[60_Troubleshooting/02_known_risks_and_debt]]
