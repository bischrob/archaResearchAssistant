# Reusability TODO (External Users)

Last reviewed: 2026-03-19

## Goal
Make `researchAssistant` installable and operable by a new user without prior local context, while preserving current Zotero-first workflow.

## Definition of Done
- A new user can run setup from a clean machine in under 30 minutes.
- A new user can ingest sample data and run a query with one documented path.
- Core workflows have automated checks in CI and a smoke test script.

## Priority Plan

## Status Snapshot (2026-03-19)
- Implemented in this pass:
  - `.env.example` created with core runtime variables and comments.
  - Root `README.md` quickstart aligned to one canonical path (`cp .env.example`, `make preflight`, `make start`, `make smoke`).
  - `scripts/preflight_check.sh` added and wired through `make preflight`.
  - `Makefile` added with reusable targets (`preflight`, `start`, `test`, `test-unit`, `test-e2e`, `smoke`, sync/ingest API examples).
  - `scripts/smoke_local_workflow.sh` added for live API health/query/diagnostics smoke checks.

## P0: Onboarding and Environment Baseline
- [x] Add a single `Quickstart` path in root `README.md`:
  - [x] prerequisites (`python`, `docker`, `neo4j`, `zotero` optional).
  - [x] one canonical startup command sequence.
  - [x] one minimal ingest+query walkthrough.
- [x] Publish a `.env.example` that is complete and validated by startup scripts.
- [x] Add `scripts/preflight_check.sh`:
  - [x] verify required binaries and versions.
  - [x] verify required directories and writable paths.
  - [x] verify API and Neo4j connectivity.
- [ ] Ensure all scripts fail with actionable error messages (no silent fallback).

## P0: Data Source Configuration (Portable Defaults)
- [ ] Standardize source selection precedence and document it:
  - [ ] `zotero_db` (preferred) then configured filesystem mode.
- [ ] Replace hardcoded path defaults in UI/API with config-derived defaults.
- [ ] Add explicit validation for Windows/WSL path mapping in sync/ingest.
- [ ] Add a sample dataset path mode so users can test without Zotero.

## P0: Packaging and Installability
- [ ] Add one script to build and install Zotero plugin end-to-end (`build + install + verify`).
- [ ] Add plugin install verification check:
  - [ ] confirm extension ID/version loaded.
  - [ ] confirm menu actions registered.
- [x] Add `make` or task-runner aliases for common workflows (`start`, `test`, `sync`, `ingest`).

## P1: API and UI Contract Clarity
- [ ] Freeze and document API contract for `/api/sync`, `/api/ingest`, `/api/query`, `/api/diagnostics`.
- [ ] Add request/response examples for success/failure/cancel states.
- [ ] Add UI state map for job lifecycle (`idle`, `running`, `cancelling`, `completed`, `failed`, `cancelled`).
- [ ] Add explicit troubleshooting page for auth/token and path-resolution errors.

## P1: Reliability and Safety
- [ ] Add idempotent sync/ingest behavior notes and tests for duplicate handling.
- [ ] Add bounded retry policy for transient failures (API/network/file lock).
- [ ] Add backup/restore runbook for Neo4j with verification steps.
- [ ] Add timeout standards per job type and document operator actions.

## P1: Test Coverage for Reuse
- [ ] Add end-to-end smoke test (`start -> sync sample -> ingest -> query -> diagnostics`).
- [x] Add live API smoke script (`health -> query -> diagnostics`) for quick environment validation.
- [ ] Add CI checks for:
  - [ ] lint/type/static checks.
  - [ ] API tests.
  - [ ] one non-flaky integration test with a tiny fixture corpus.
- [ ] Add fixture-based Zotero DB test path for deterministic sync tests.

## P2: Distribution and Team Adoption
- [ ] Create release checklist and versioning policy (backend + plugin compatibility matrix).
- [ ] Publish changelog format and migration notes for breaking config changes.
- [ ] Add architecture diagram focused on deploy/use by new contributors.
- [ ] Add “known limitations” section with supported OS/deployment modes.

## Suggested Milestones
- M0 (1-2 days): P0 onboarding + config + packaging baseline.
- M1 (2-4 days): P1 contract clarity + reliability + core tests.
- M2 (1-2 days): P2 release hygiene and contributor docs.

## Acceptance Checks
- [ ] Fresh-machine install validated by someone who has never run the project.
- [ ] No hardcoded user-specific paths remain in default runtime path.
- [ ] Quickstart and runbook produce identical results on two environments.
- [ ] CI catches broken core workflow before merge.
