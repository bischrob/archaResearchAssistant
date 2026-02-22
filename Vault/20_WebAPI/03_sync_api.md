# Web API: Sync Endpoints

## Source file
- `webapp/main.py` (`/api/sync*`)

## Endpoints
- `POST /api/sync`
- `GET /api/sync/status`
- `POST /api/sync/stop`

## Sync execution details
- Runs `scripts/sync_pdfs_from_gdrive.sh` with optional `--dry-run`.
- Uses `subprocess.Popen` and reader threads to capture stdout/stderr.
- Maintains bounded in-memory logs (last ~4000 lines; response tail limited).
- Progress uses remote count estimate (`rclone lsf`) when available.

## Cancellation
- Stop endpoint sets cancel flag and terminates process.
- If process ignores terminate, code escalates to kill.

## Failure modes
- Missing sync script.
- `rclone` errors from script.
- Nonzero script exit status surfaces as runtime error with tail details.

## Test note
Current suite has one failing sync stop test under `PYTHONPATH=.` due mock/implementation mismatch around process stream handling.

## Related
- [[40_Scripts/02_shell_scripts]]
- [[50_Testing/02_current_test_status_2026-02-21]]
