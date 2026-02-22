# Test Status Snapshot (2026-02-21)

## Command 1
`pytest -q`

## Result
- Fails during collection.
- Error: `ModuleNotFoundError: No module named 'src'` in all test modules.

## Root cause
Project is not installed as package and tests rely on `from src...` imports; repository root is not automatically on `PYTHONPATH` in this environment.

## Command 2
`PYTHONPATH=. pytest -q`

## Result
- 29 passed
- 1 failed (`tests/test_web_api.py::test_sync_start_status_and_stop`)

## Failed test details
- Expected final status in `{"cancelled", "completed"}`.
- Actual final status was `failed`.
- Likely due fake `Popen` object mismatch with implementation assumptions around stream handling.

## Practical interpretation
- Core logic mostly validated under patched conditions.
- CI reliability requires explicit `PYTHONPATH=.` or packaging fix.
- Sync cancellation test should be updated to match implementation behavior/mocks.

## Recommended fixes
1. Add `pythonpath = .` in `pytest.ini` or package-install project for tests.
2. Harden `test_sync_start_status_and_stop` fake process to provide expected `stdout`/`stderr` stream semantics.

## Related
- [[20_WebAPI/03_sync_api]]
- [[60_Troubleshooting/01_symptom_to_cause_matrix]]
