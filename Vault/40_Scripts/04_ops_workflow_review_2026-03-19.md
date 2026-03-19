# Ops + Workflow Review (2026-03-19)

## Focus
Review of startup/run scripts, Docker/runtime config drift, backup safety, sync workflow reliability, and SOL training reproducibility.

## Key findings
### High
1. SOL training scripts can race on shared env creation/install (no lock protection).
2. `USE_4BIT` marker reuse can cause nondeterministic dependency state.
3. Backup script can leave Neo4j down on script failure (no fail-fast trap/restart guarantee).

### Medium
1. Operational startup currently uses `--reload`, which is unstable for long-running workflows.
2. Port-probe startup has TOCTOU race (checked open, later bind can still fail).
3. Legacy GDrive sync with `--ignore-existing` can leave changed upstream files stale.
4. Docs/config drift around runtime defaults (for example parser mode) persists.
5. Hardcoded path/secrets defaults increase host drift and security exposure.
6. Training provenance is incomplete for strict reproducibility (missing full env + dataset hashing context).

## Review action package
### M1
1. Script safety hardening
- Acceptance: backup path always restarts Neo4j on failure; startup has deterministic non-reload mode for operations.
- Tests: shell smoke tests for failure-path cleanup/restart.

2. Training env locking and determinism guardrails
- Acceptance: concurrent sbatch runs cannot mutate shared env concurrently.
- Tests: lock acquisition/release behavior and dependency marker integrity checks.

3. Sync freshness and manifesting
- Acceptance: sync path can detect changed upstream files and records immutable run manifest/checksum.
- Tests: changed file scenario with refresh verification.

### M2
1. Config/doc parity and secret hygiene
- Acceptance: Vault/README defaults match runtime config; no hardcoded production credentials in defaults.
- Tests: docs drift checklist in review gate.

2. Training provenance completeness
- Acceptance: each run records git SHA, dependency snapshot, dataset hashes, runtime hardware context, and arguments.
- Tests: training run metadata schema checks.

## Ops reliability checklist
- [ ] Startup preflight verifies Docker, Neo4j, Python deps, required env vars.
- [ ] Backup path is fail-safe and restart-safe.
- [ ] Training scripts are lock-protected and reproducible.
- [ ] Sync workflows produce auditable manifests.
- [ ] Runtime/docs parity review is part of release checklist.

## Status Updates
- `run_web_gui.sh`: deterministic non-reload mode is the default, with `UVICORN_RELOAD=1` reserved for interactive development.
- `backup_neo4j.sh`: restart-on-failure guard is in place around the dump path.
- SOL training sbatch scripts: shared env setup is serialized with a lock to avoid concurrent mutation.
- `sync_pdfs_from_gdrive.sh`: manifest output and explicit stale-ignore warning are added; `SYNC_REFRESH_CHANGED=1` enables checksum-based refresh for existing files.

## Owner
- Ops/workflow owner (startup, scripts, training pipeline)

## Related
- [[40_Scripts/01_cli_scripts]]
- [[40_Scripts/02_shell_scripts]]
- [[40_Scripts/03_docker_services]]
- [[00_Project/05_startup_runbook]]
- [[60_Troubleshooting/08_codebase_workflow_review_2026-03-19]]
