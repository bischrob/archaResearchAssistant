# PowerShell And Linux Compatibility Plan

This checklist tracks the migration from bash-first workflow wrappers to shared Python orchestration with thin OS-specific launchers.

## Goals

- make the day-to-day operator workflow work from both PowerShell and Linux shells
- keep `ra` as the canonical interface
- reduce duplicate shell logic
- preserve safe handling of local config and secrets

## Phase 1: Shared Python runtime checks

- [x] Add Python-native interpreter resolution shared by future wrappers.
- [x] Add Python-native `ra preflight`.
- [x] Keep `scripts/preflight_check.sh` as a compatibility wrapper around the Python implementation.
- [x] Add PowerShell wrapper `scripts/preflight_check.ps1`.

## Phase 2: Shared startup orchestration

- [x] Move `start.sh` orchestration into Python.
- [x] Keep `start.sh` as a thin Linux wrapper.
- [x] Add `start.ps1` as a thin PowerShell wrapper.
- [x] Detect Docker/Compose uniformly from Python.
- [x] Support foreground and background startup on both platforms.

## Phase 3: Cross-platform repo wrapper

- [x] Keep `scripts/run_ra_from_repo.sh` thin.
- [x] Add `scripts/run_ra_from_repo.ps1`.
- [x] Document `ra` as the preferred cross-platform interface.

## Phase 4: Tests

- [ ] Replace bash-only smoke expectations with shared CLI behavior tests.
- [ ] Add tests for Python interpreter resolution on Windows-style paths.
- [ ] Add tests for `ra preflight`.
- [x] Add wrapper smoke tests for `.sh` and `.ps1`.

## Phase 5: Docs

- [x] Update README examples for Linux and PowerShell.
- [x] Add Windows/PowerShell setup notes to `docs/NEW_USER_SETUP.md`.
- [x] Update operator runbook to prefer `ra` for portable workflows.

## Follow-Up Completed

- [x] Add a PowerShell-native task runner comparable to the Linux `Makefile`.
