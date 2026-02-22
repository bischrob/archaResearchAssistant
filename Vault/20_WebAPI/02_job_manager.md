# Web API: Job Manager Concurrency Model

## Source file
- `webapp/main.py` (`JobState`, `JobManager`)

## Responsibility
Manage long-running tasks (`sync`, `ingest`, `query`) with start/stop/status semantics.

## Internal model
- One `JobState` per job name.
- Global lock protects reads/writes to job state.
- `start()` spawns daemon thread; rejects concurrent start with 409.
- `stop()` sets cancellation event and terminates child process if present.

## Progress reporting
- Job states include `progress_percent` and `progress_message`.
- Ingest and sync update progress periodically.

## Cancellation behavior
- Cooperative cancellation for ingest/query via callback checks.
- Process termination path for sync (`subprocess.Popen`).

## Failure semantics
- Uncaught runner exceptions set status to `failed` unless cancellation event is set.
- Result payload may be partial during batched ingest.

## Design caveats
- In-memory only; job state resets on process restart.
- No persistent queue or backpressure.
- Shared lock is internal but used externally in a few places for partial result updates.

## Related
- [[20_WebAPI/03_sync_api]]
- [[20_WebAPI/04_ingest_api]]
