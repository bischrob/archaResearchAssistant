#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import typer

app = typer.Typer(help="Repo-native operator CLI for archaResearch Assistant.")
sync_app = typer.Typer(help="Sync Zotero/filesystem PDFs into the graph.")
app.add_typer(sync_app, name="sync")

ROOT = Path(__file__).resolve().parents[2]
START_SCRIPT = ROOT / "start.sh"
DEFAULT_BASE_URL = os.getenv("RA_BASE_URL", "http://192.168.0.37:8001").rstrip("/")
DEFAULT_TIMEOUT = float(os.getenv("RA_HTTP_TIMEOUT", "30"))
DEFAULT_ASK_TIMEOUT = float(os.getenv("RA_ASK_TIMEOUT", "300"))
DEFAULT_POLL_INTERVAL = float(os.getenv("RA_POLL_INTERVAL", "1.0"))
DEFAULT_ASK_SCORE_THRESHOLD = float(os.getenv("RA_ASK_SCORE_THRESHOLD", "1.0"))
DEFAULT_ASK_RETRIEVAL_POOL = int(os.getenv("RA_ASK_RETRIEVAL_POOL", "30"))


class CLIError(RuntimeError):
    pass


class APIClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        token = os.getenv("API_BEARER_TOKEN", "").strip()
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> dict[str, Any]:
        return self._request("POST", path, **kwargs)

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            response = self.session.request(method, self._url(path), timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            raise CLIError(f"Request failed: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {"status_code": response.status_code, "text": response.text}
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else None
            raise CLIError(f"API {method} {path} failed ({response.status_code}): {detail or payload}")
        if not isinstance(payload, dict):
            raise CLIError(f"API {method} {path} returned non-object JSON: {payload!r}")
        return payload


class Spinner:
    def __init__(self, message: str, *, enabled: bool) -> None:
        self.message = message
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "Spinner":
        if not self.enabled:
            return self
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.5)
        typer.echo("\r" + (" " * (len(self.message) + 4)) + "\r", err=True, nl=False)

    def _run(self) -> None:
        frames = "|/-\\"
        idx = 0
        while not self._stop.wait(0.1):
            typer.echo(f"\r{self.message} {frames[idx % len(frames)]}", err=True, nl=False)
            idx += 1


class CLIContext:
    def __init__(self, base_url: str, timeout: float, json_output: bool) -> None:
        self.client = APIClient(base_url=base_url, timeout=timeout)
        self.json_output = json_output

    @property
    def stderr_is_tty(self) -> bool:
        stream = getattr(sys.stderr, "isatty", lambda: False)
        return bool(stream())

    def emit(self, payload: Any) -> None:
        if self.json_output:
            typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return
        typer.echo(json.dumps(payload, indent=2, default=str))

    def emit_text(self, text: str) -> None:
        typer.echo(text)

    def note(self, message: str) -> None:
        if not self.json_output:
            typer.echo(message, err=True)

    def success(self, message: str) -> None:
        if not self.json_output:
            typer.secho(message, err=True, fg=typer.colors.GREEN)

    def spinner(self, message: str):
        if self.json_output:
            return nullcontext()
        enabled = self.stderr_is_tty
        if not enabled:
            self.note(message)
        return Spinner(message, enabled=enabled)


@app.callback()
def main(
    ctx: typer.Context,
    base_url: str = typer.Option(DEFAULT_BASE_URL, help="API base URL."),
    timeout: float = typer.Option(DEFAULT_TIMEOUT, min=1.0, help="HTTP timeout in seconds."),
    json_output: bool = typer.Option(False, "--json", help="Emit raw JSON output."),
) -> None:
    ctx.obj = CLIContext(base_url=base_url, timeout=timeout, json_output=json_output)


def require_ctx(ctx: typer.Context) -> CLIContext:
    if not isinstance(ctx.obj, CLIContext):
        raise CLIError("CLI context is not initialized.")
    return ctx.obj


def _first_value(payload: Any, *paths: tuple[str, ...] | str) -> Any:
    for path in paths:
        keys = (path,) if isinstance(path, str) else path
        current = payload
        for key in keys:
            if not isinstance(current, dict) or key not in current:
                current = None
                break
            current = current[key]
        if current is not None:
            return current
    return None


def _coerce_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit() or (stripped.startswith("-") and stripped[1:].isdigit()):
            return int(stripped)
    return None


def _format_count(label: str, value: Any) -> str | None:
    parsed = _coerce_int(value)
    if parsed is None:
        return None
    return f"- {label}: {parsed}"


def _format_diagnostics_summary(payload: dict[str, Any]) -> str:
    lines: list[str] = ["Diagnostics"]
    ok = payload.get("ok")
    if ok is not None:
        lines[0] = f"Diagnostics ({'ok' if ok else 'issues detected'})"

    source_mode = _first_value(payload, "source_mode", ("sync", "source_mode"), ("ingest", "source_mode"))
    metadata_backend = _first_value(payload, "metadata_backend", ("config", "metadata_backend"))
    if source_mode or metadata_backend:
        detail = []
        if source_mode:
            detail.append(f"source_mode={source_mode}")
        if metadata_backend:
            detail.append(f"metadata_backend={metadata_backend}")
        lines.append(f"- Mode: {', '.join(detail)}")

    count_lines = [
        _format_count("Zotero attachment rows", _first_value(payload, "attachment_rows", ("zotero", "attachment_rows"), ("stats", "attachment_rows"), ("stats", "zotero_attachment_rows"))),
        _format_count("Ingest candidates", _first_value(payload, "ingest_candidates", ("sync", "ingest_candidates"), ("stats", "ingest_candidates"), ("zotero", "ingest_candidates"))),
        _format_count("Resolvable attachments", _first_value(payload, "resolvable", ("resolution", "resolvable"), ("stats", "resolvable"), ("zotero", "resolvable"))),
        _format_count("Missing attachments", _first_value(payload, "missing", ("resolution", "missing"), ("stats", "missing"), ("zotero", "missing"))),
        _format_count("Already ingested", _first_value(payload, "already_ingested", ("sync", "already_ingested"), ("stats", "already_ingested"))),
    ]
    lines.extend(line for line in count_lines if line)

    local_matched = _coerce_int(_first_value(payload, "local_pdfs_matched", ("filesystem", "matched"), ("stats", "local_pdfs_matched")))
    local_total = _coerce_int(_first_value(payload, "local_pdfs_total", ("filesystem", "total"), ("stats", "local_pdfs_total")))
    if source_mode == "zotero_db":
        if local_matched is not None or local_total is not None:
            matched_display = local_matched if local_matched is not None else "?"
            total_display = local_total if local_total is not None else "?"
            lines.append(f"- Filesystem local PDF match scan: {matched_display}/{total_display} (informational only; Zotero DB is the ingest source)")
        else:
            lines.append("- Filesystem local PDF match scan: n/a (Zotero DB mode)")
    elif local_matched is not None or local_total is not None:
        matched_display = local_matched if local_matched is not None else "?"
        total_display = local_total if local_total is not None else "?"
        lines.append(f"- Local PDFs matched: {matched_display}/{total_display}")

    checks = payload.get("checks")
    if isinstance(checks, list) and checks:
        failing_checks = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            if check.get("ok") is False:
                name = check.get("name") or check.get("check") or "unnamed-check"
                detail = check.get("detail") or check.get("message")
                failing_checks.append(f"{name}: {detail}" if detail else str(name))
        if failing_checks:
            lines.append("- Failing checks:")
            lines.extend(f"  - {item}" for item in failing_checks)

    return "\n".join(lines)


def _format_status_summary(payload: dict[str, Any]) -> str:
    lines = [f"archaResearch Assistant @ {payload.get('base_url', 'unknown')}"]
    if not payload.get("reachable"):
        if payload.get("error"):
            lines.append(f"- Reachable: no ({payload['error']})")
        else:
            lines.append("- Reachable: no")
        return "\n".join(lines)

    lines.append("- Reachable: yes")
    version = payload.get("version")
    if isinstance(version, dict) and version.get("version"):
        lines.append(f"- Version: {version['version']}")
    health = payload.get("health")
    if isinstance(health, dict):
        status = health.get("status")
        stats = health.get("stats")
        stat_suffix = ""
        if isinstance(stats, dict) and stats:
            stat_parts = [f"{key}={value}" for key, value in sorted(stats.items())]
            stat_suffix = f" ({', '.join(stat_parts)})"
        if status:
            lines.append(f"- Health: {status}{stat_suffix}")
    diagnostics = payload.get("diagnostics")
    if isinstance(diagnostics, dict):
        lines.append(_format_diagnostics_summary(diagnostics))
    jobs = payload.get("jobs")
    if isinstance(jobs, dict) and jobs:
        lines.append("Jobs")
        for name in ("sync", "ingest", "query"):
            job = jobs.get(name)
            if not isinstance(job, dict):
                continue
            detail = job.get("status") or job.get("error") or "unknown"
            lines.append(f"- {name}: {detail}")
    return "\n".join(lines)


def _extract_job_stage(payload: dict[str, Any]) -> str | None:
    for key in ("stage", "phase", "message", "detail"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("stage", "phase", "message", "detail"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _extract_job_progress(payload: dict[str, Any]) -> str | None:
    for current_key, total_key in (("completed", "total"), ("processed", "total"), ("done", "total"), ("current", "total")):
        current = _coerce_int(payload.get(current_key))
        total = _coerce_int(payload.get(total_key))
        if current is not None and total is not None:
            return f"{current}/{total}"
    result = payload.get("result")
    if isinstance(result, dict):
        for current_key, total_key in (("completed", "total"), ("processed", "total"), ("done", "total"), ("current", "total")):
            current = _coerce_int(result.get(current_key))
            total = _coerce_int(result.get(total_key))
            if current is not None and total is not None:
                return f"{current}/{total}"
    return None


def _build_progress_message(label: str, payload: dict[str, Any]) -> str:
    status = payload.get("status") or "running"
    parts = [label, f"status={status}"]
    stage = _extract_job_stage(payload)
    if stage:
        parts.append(f"stage={stage}")
    progress = _extract_job_progress(payload)
    if progress:
        parts.append(f"progress={progress}")
    request_id = payload.get("request_id")
    if request_id:
        parts.append(f"request_id={request_id}")
    return " | ".join(parts)


class AsyncProgressReporter:
    def __init__(self, cli: CLIContext, label: str) -> None:
        self.cli = cli
        self.label = label
        self._last_message: str | None = None

    def started(self, payload: dict[str, Any]) -> None:
        if self.cli.json_output or payload.get("status") != "running":
            return
        if self.cli.stderr_is_tty:
            return
        self._emit(payload, prefix=f"Started {self.label}: ")

    def update(self, payload: dict[str, Any]) -> None:
        if self.cli.json_output or self.cli.stderr_is_tty:
            return
        self._emit(payload)

    def _emit(self, payload: dict[str, Any], *, prefix: str = "") -> None:
        message = _build_progress_message(self.label, payload)
        if message == self._last_message:
            return
        self._last_message = message
        self.cli.note(f"{prefix}{message}")


def wait_for_job(
    client: APIClient,
    status_path: str,
    poll_interval: float,
    timeout_s: float,
    *,
    on_update: callable | None = None,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        payload = client.get(status_path)
        last_payload = payload
        if on_update is not None:
            on_update(payload)
        if payload.get("status") != "running":
            return payload
        time.sleep(poll_interval)
    raise CLIError(f"Timed out waiting for job at {status_path}. Last payload: {last_payload}")


def run_async_command(
    client: APIClient,
    start_path: str,
    status_path: str,
    payload: dict[str, Any],
    *,
    wait: bool,
    poll_interval: float,
    timeout_s: float,
    on_started: callable | None = None,
    on_update: callable | None = None,
) -> dict[str, Any]:
    started = client.post(start_path, json=payload)
    if on_started is not None:
        on_started(started)
    if not wait or started.get("status") != "running":
        return started
    return wait_for_job(client, status_path, poll_interval=poll_interval, timeout_s=timeout_s, on_update=on_update)


def _job_statuses(client: APIClient) -> dict[str, Any]:
    job_paths = {
        "sync": "/api/sync/status",
        "ingest": "/api/ingest/status",
        "query": "/api/query/status",
    }
    jobs: dict[str, Any] = {}
    for name, path in job_paths.items():
        try:
            jobs[name] = client.get(path)
        except CLIError as exc:
            jobs[name] = {"ok": False, "error": str(exc)}
    return jobs


@app.command()
def status(
    ctx: typer.Context,
    include_jobs: bool = typer.Option(True, help="Include async job status snapshots."),
) -> None:
    cli = require_ctx(ctx)
    payload: dict[str, Any] = {
        "base_url": cli.client.base_url,
        "reachable": False,
    }
    try:
        payload["version"] = cli.client.get("/api/version")
        payload["health"] = cli.client.get("/api/health")
        payload["diagnostics"] = cli.client.get("/api/diagnostics")
        if include_jobs:
            payload["jobs"] = _job_statuses(cli.client)
        payload["reachable"] = True
    except CLIError as exc:
        payload["error"] = str(exc)
    if cli.json_output:
        cli.emit(payload)
    else:
        cli.emit_text(_format_status_summary(payload))
    if not payload["reachable"]:
        raise typer.Exit(code=1)


@app.command()
def diagnostics(ctx: typer.Context) -> None:
    cli = require_ctx(ctx)
    payload = cli.client.get("/api/diagnostics")
    if cli.json_output:
        cli.emit(payload)
        return
    cli.emit_text(_format_diagnostics_summary(payload))


@app.command()
def start(
    ctx: typer.Context,
    background: bool = typer.Option(True, "--background/--foreground", help="Start detached by default."),
    wait: bool = typer.Option(True, help="Wait for the API health endpoint after launching."),
    wait_timeout: float = typer.Option(120.0, min=1.0, help="Startup wait timeout in seconds."),
    poll_interval: float = typer.Option(DEFAULT_POLL_INTERVAL, min=0.2, help="Health poll interval."),
    port: int | None = typer.Option(None, min=1, max=65535, help="PORT override for start.sh."),
    host: str | None = typer.Option(None, help="HOST override for uvicorn."),
    skip_preflight: bool = typer.Option(False, help="Set RUN_PREFLIGHT=0 for this launch."),
) -> None:
    cli = require_ctx(ctx)
    if not START_SCRIPT.exists():
        raise typer.BadParameter(f"Start script not found: {START_SCRIPT}")

    env = os.environ.copy()
    if port is not None:
        env["PORT"] = str(port)
    if host:
        env["HOST"] = host
    if skip_preflight:
        env["RUN_PREFLIGHT"] = "0"

    command = ["bash", str(START_SCRIPT)]
    launched_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    cli.note(f"Starting archaResearch Assistant from {ROOT}")
    if background:
        logs_dir = ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        log_path = logs_dir / f"ra-start-{stamp}.log"
        with open(log_path, "ab") as log_handle:
            proc = subprocess.Popen(
                command,
                cwd=ROOT,
                env=env,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        payload: dict[str, Any] = {
            "ok": True,
            "mode": "background",
            "pid": proc.pid,
            "log_path": str(log_path),
            "command": command,
            "launched_at": launched_at,
        }
        cli.note(f"Launched background process pid={proc.pid}; logging to {log_path}")
        if wait:
            deadline = time.time() + wait_timeout
            last_error = None
            with cli.spinner(f"Waiting for API health at {cli.client.base_url}/api/health"):
                while time.time() < deadline:
                    if proc.poll() is not None:
                        raise CLIError(f"start.sh exited early with code {proc.returncode}. See {log_path}")
                    try:
                        payload["health"] = cli.client.get("/api/health", timeout=5)
                        payload["ready"] = True
                        break
                    except CLIError as exc:
                        last_error = str(exc)
                        time.sleep(poll_interval)
                else:
                    payload["ready"] = False
                    payload["wait_error"] = last_error or "Timed out waiting for /api/health"
                    cli.emit(payload)
                    raise typer.Exit(code=1)
            cli.success("API is healthy.")
        else:
            cli.note("Skipping API health wait (--no-wait).")
        cli.emit(payload)
        return

    cli.note("Running start.sh in the foreground; output will stream below.")
    proc = subprocess.run(command, cwd=ROOT, env=env, check=False)
    raise typer.Exit(code=proc.returncode)


@sync_app.command("dry-run")
def sync_dry_run(
    ctx: typer.Context,
    source_mode: str = typer.Option("zotero_db", help="filesystem or zotero_db."),
    source_dir: str | None = typer.Option(None, help="Override source directory."),
    run_ingest: bool = typer.Option(False, help="Request ingest after sync (normally false for dry-run)."),
    wait: bool = typer.Option(True, help="Poll until the sync job reaches a terminal state."),
    wait_timeout: float = typer.Option(1800.0, min=1.0, help="Job wait timeout in seconds."),
    poll_interval: float = typer.Option(DEFAULT_POLL_INTERVAL, min=0.2, help="Job poll interval."),
) -> None:
    cli = require_ctx(ctx)
    label = "sync dry-run"
    progress = AsyncProgressReporter(cli, label)
    result = run_async_command(
        cli.client,
        "/api/sync",
        "/api/sync/status",
        {k: v for k, v in {
            "dry_run": True,
            "source_mode": source_mode,
            "run_ingest": run_ingest,
            "source_dir": source_dir,
        }.items() if v is not None},
        wait=wait,
        poll_interval=poll_interval,
        timeout_s=wait_timeout,
        on_started=progress.started,
        on_update=progress.update,
    )
    cli.emit(result)


@sync_app.command("ingest")
def sync_ingest(
    ctx: typer.Context,
    source_mode: str = typer.Option("zotero_db", help="filesystem or zotero_db."),
    source_dir: str | None = typer.Option(None, help="Override source directory."),
    ingest_skip_existing: bool = typer.Option(True, help="Skip already ingested PDFs."),
    wait: bool = typer.Option(True, help="Poll until the sync job reaches a terminal state."),
    wait_timeout: float = typer.Option(7200.0, min=1.0, help="Job wait timeout in seconds."),
    poll_interval: float = typer.Option(DEFAULT_POLL_INTERVAL, min=0.2, help="Job poll interval."),
) -> None:
    cli = require_ctx(ctx)
    label = "sync ingest"
    progress = AsyncProgressReporter(cli, label)
    payload = {
        "dry_run": False,
        "source_mode": source_mode,
        "run_ingest": True,
        "ingest_skip_existing": ingest_skip_existing,
    }
    if source_dir:
        payload["source_dir"] = source_dir
    result = run_async_command(
        cli.client,
        "/api/sync",
        "/api/sync/status",
        payload,
        wait=wait,
        poll_interval=poll_interval,
        timeout_s=wait_timeout,
        on_started=progress.started,
        on_update=progress.update,
    )
    cli.emit(result)


@app.command("zotero-search")
def zotero_search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search text for Zotero-backed PDF items."),
    limit: int = typer.Option(20, min=1, max=500, help="Maximum results."),
    offset: int = typer.Option(0, min=0, max=5000, help="Result offset."),
    available_only: bool = typer.Option(True, help="Only show resolvable PDFs."),
) -> None:
    cli = require_ctx(ctx)
    result = cli.client.post(
        "/api/zotero/items/search",
        json={
            "query": query,
            "limit": limit,
            "offset": offset,
            "available_only": available_only,
        },
    )
    cli.emit(result)


@app.command("zotero-ingest")
def zotero_ingest(
    ctx: typer.Context,
    zotero_persistent_ids: list[str] = typer.Argument(..., help="One or more Zotero persistent IDs."),
    reingest: bool = typer.Option(False, help="Reingest even if already present."),
    wait: bool = typer.Option(True, help="Poll until ingest reaches a terminal state."),
    wait_timeout: float = typer.Option(7200.0, min=1.0, help="Job wait timeout in seconds."),
    poll_interval: float = typer.Option(DEFAULT_POLL_INTERVAL, min=0.2, help="Job poll interval."),
) -> None:
    cli = require_ctx(ctx)
    label = "zotero ingest"
    progress = AsyncProgressReporter(cli, label)
    result = run_async_command(
        cli.client,
        "/api/zotero/items/ingest",
        "/api/ingest/status",
        {"zotero_persistent_ids": zotero_persistent_ids, "reingest": reingest},
        wait=wait,
        poll_interval=poll_interval,
        timeout_s=wait_timeout,
        on_started=progress.started,
        on_update=progress.update,
    )
    cli.emit(result)


@app.command()
def query(
    ctx: typer.Context,
    text: str = typer.Argument(..., help="Query text."),
    limit: int = typer.Option(20, min=1, max=20),
    limit_scope: str = typer.Option("papers", help="papers or chunks."),
    chunks_per_paper: int = typer.Option(8, min=1, max=20),
    score_threshold: float | None = typer.Option(DEFAULT_ASK_SCORE_THRESHOLD, min=0.0, help="Semantic relevance threshold used by default."),
    wait: bool = typer.Option(True, help="Poll until the query reaches a terminal state."),
    wait_timeout: float = typer.Option(600.0, min=1.0),
    poll_interval: float = typer.Option(DEFAULT_POLL_INTERVAL, min=0.2),
) -> None:
    cli = require_ctx(ctx)
    label = "query"
    progress = AsyncProgressReporter(cli, label)
    result = run_async_command(
        cli.client,
        "/api/query",
        "/api/query/status",
        {
            "query": text,
            "limit": limit,
            "limit_scope": limit_scope,
            "chunks_per_paper": chunks_per_paper,
            "score_threshold": score_threshold,
        },
        wait=wait,
        poll_interval=poll_interval,
        timeout_s=wait_timeout,
        on_started=progress.started,
        on_update=progress.update,
    )
    cli.emit(result)


@app.command()
def ask(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Grounded question to answer."),
    rag_results: int | None = typer.Option(None, min=1, max=30, help="Fixed top-N chunk override."),
    score_threshold: float | None = typer.Option(DEFAULT_ASK_SCORE_THRESHOLD, min=0.0, help="Semantic relevance threshold used by default."),
    retrieval_pool: int = typer.Option(DEFAULT_ASK_RETRIEVAL_POOL, min=1, max=100, help="Candidate retrieval pool before thresholding."),
    model: str | None = typer.Option(None, help="Optional answer model override."),
    enforce_citations: bool = typer.Option(True, help="Require cited grounding in the answer."),
    preprocess_search: bool = typer.Option(True, help="Allow query rewriting before retrieval."),
) -> None:
    cli = require_ctx(ctx)
    cli.note("Submitting ask request to /api/ask")
    ask_timeout = DEFAULT_ASK_TIMEOUT if cli.client.timeout == DEFAULT_TIMEOUT else cli.client.timeout
    payload = {
        "question": question,
        "rag_results": rag_results,
        "score_threshold": score_threshold,
        "retrieval_pool": retrieval_pool,
        "model": model,
        "enforce_citations": enforce_citations,
        "preprocess_search": preprocess_search,
    }
    result = cli.client.post(
        "/api/ask",
        timeout=ask_timeout,
        json={key: value for key, value in payload.items() if value is not None},
    )
    cli.success("Ask request completed.")
    cli.emit(result)


@app.command()
def article(
    ctx: typer.Context,
    citekey: str = typer.Argument(..., help="Article citekey."),
    chunk_limit: int = typer.Option(3, min=1, max=20),
) -> None:
    cli = require_ctx(ctx)
    result = cli.client.get(f"/api/article/{citekey}", params={"chunk_limit": chunk_limit})
    cli.emit(result)


@app.command()
def articles(
    ctx: typer.Context,
    citekeys: list[str] = typer.Argument(..., help="One or more citekeys."),
    chunk_limit: int = typer.Option(3, min=1, max=20),
) -> None:
    cli = require_ctx(ctx)
    result = cli.client.post(
        "/api/articles/by-citekeys",
        json={"citekeys": citekeys, "chunk_limit": chunk_limit},
    )
    cli.emit(result)


def entrypoint() -> None:
    try:
        app()
    except CLIError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    entrypoint()
