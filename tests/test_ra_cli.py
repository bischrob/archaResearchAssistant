import json
import runpy
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rag import cli as ra


runner = CliRunner()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.headers = {}
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url, "timeout": timeout, **kwargs})
        key = (method.upper(), url)
        value = self.routes[key]
        if callable(value):
            return value(method=method.upper(), url=url, timeout=timeout, **kwargs)
        return value


@pytest.fixture
def fake_session_factory(monkeypatch):
    created = []

    def factory(routes):
        session = FakeSession(routes)
        created.append(session)
        monkeypatch.setattr(ra.requests, "Session", lambda: session)
        return session

    return factory, created


def test_status_reports_reachable_with_job_snapshots(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("GET", "http://127.0.0.1:8000/api/version"): FakeResponse(payload={"status": "ok", "version": "1"}),
            ("GET", "http://127.0.0.1:8000/api/health"): FakeResponse(payload={"status": "ok", "stats": {"articles": 2}}),
            ("GET", "http://127.0.0.1:8000/api/diagnostics"): FakeResponse(payload={"ok": True, "checks": []}),
            ("GET", "http://127.0.0.1:8000/api/sync/status"): FakeResponse(payload={"status": "idle"}),
            ("GET", "http://127.0.0.1:8000/api/ingest/status"): FakeResponse(payload={"status": "running"}),
            ("GET", "http://127.0.0.1:8000/api/query/status"): FakeResponse(payload={"status": "completed"}),
        }
    )

    result = runner.invoke(ra.app, ["--json", "status"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reachable"] is True
    assert payload["health"]["stats"]["articles"] == 2
    assert payload["jobs"]["ingest"]["status"] == "running"
    assert created[0].calls[0]["timeout"] == ra.DEFAULT_TIMEOUT


def test_status_exits_nonzero_when_api_unreachable(fake_session_factory):
    factory, _ = fake_session_factory

    def fail_request(**kwargs):
        raise ra.requests.ConnectionError("boom")

    factory({("GET", "http://127.0.0.1:8000/api/version"): fail_request})
    result = runner.invoke(ra.app, ["--json", "status"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["reachable"] is False
    assert "Request failed" in payload["error"]


def test_diagnostics_human_output_prefers_zotero_counts_over_local_pdf_match_placeholder(fake_session_factory):
    factory, _ = fake_session_factory
    factory(
        {
            ("GET", "http://127.0.0.1:8000/api/diagnostics"): FakeResponse(
                payload={
                    "ok": True,
                    "source_mode": "zotero_db",
                    "zotero": {"attachment_rows": 42, "ingest_candidates": 11, "resolvable": 9, "missing": 2},
                }
            )
        }
    )

    result = runner.invoke(ra.app, ["diagnostics"])
    assert result.exit_code == 0, result.stdout
    assert "source_mode=zotero_db" in result.stdout
    assert "Zotero attachment rows: 42" in result.stdout
    assert "Ingest candidates: 11" in result.stdout
    assert "Resolvable attachments: 9" in result.stdout
    assert "Missing attachments: 2" in result.stdout
    assert "Filesystem local PDF match scan: n/a (Zotero DB mode)" in result.stdout
    assert "0/0 local PDFs matched" not in result.stdout


def test_status_human_output_marks_filesystem_counts_as_informational_in_zotero_mode(fake_session_factory):
    factory, _ = fake_session_factory
    factory(
        {
            ("GET", "http://127.0.0.1:8000/api/version"): FakeResponse(payload={"status": "ok", "version": "1"}),
            ("GET", "http://127.0.0.1:8000/api/health"): FakeResponse(payload={"status": "ok", "stats": {"articles": 2}}),
            ("GET", "http://127.0.0.1:8000/api/diagnostics"): FakeResponse(
                payload={
                    "ok": True,
                    "source_mode": "zotero_db",
                    "zotero": {"attachment_rows": 7, "ingest_candidates": 3},
                    "filesystem": {"matched": 0, "total": 0},
                }
            ),
            ("GET", "http://127.0.0.1:8000/api/sync/status"): FakeResponse(payload={"status": "idle"}),
            ("GET", "http://127.0.0.1:8000/api/ingest/status"): FakeResponse(payload={"status": "idle"}),
            ("GET", "http://127.0.0.1:8000/api/query/status"): FakeResponse(payload={"status": "idle"}),
        }
    )

    result = runner.invoke(ra.app, ["status"])
    assert result.exit_code == 0, result.stdout
    assert "Diagnostics (ok)" in result.stdout
    assert "Zotero attachment rows: 7" in result.stdout
    assert "Ingest candidates: 3" in result.stdout
    assert "Filesystem local PDF match scan: 0/0 (informational only; Zotero DB is the ingest source)" in result.stdout


def test_sync_dry_run_waits_for_terminal_status(fake_session_factory):
    factory, created = fake_session_factory
    states = iter(
        [
            FakeResponse(payload={"status": "running", "request_id": "abc"}),
            FakeResponse(payload={"status": "completed", "result": {"ok": True, "dry_run": True}}),
        ]
    )

    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/sync"): FakeResponse(payload={"status": "running", "request_id": "abc"}),
            ("GET", "http://127.0.0.1:8000/api/sync/status"): lambda **kwargs: next(states),
        }
    )

    result = runner.invoke(ra.app, ["--json", "sync", "dry-run", "--wait", "--poll-interval", "0.2"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    post_call = created[0].calls[0]
    assert post_call["json"]["dry_run"] is True
    assert post_call["json"]["run_ingest"] is False


def test_sync_ingest_background_returns_initial_job_state(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/sync"): FakeResponse(payload={"status": "running", "request_id": "job-1"}),
        }
    )

    result = runner.invoke(ra.app, ["--json", "sync", "ingest", "--no-wait", "--source-mode", "filesystem", "--source-dir", "/tmp/pdfs"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "running"
    post_call = created[0].calls[0]
    assert post_call["json"]["dry_run"] is False
    assert post_call["json"]["run_ingest"] is True
    assert post_call["json"]["source_mode"] == "filesystem"
    assert post_call["json"]["source_dir"] == "/tmp/pdfs"


def test_zotero_ingest_posts_ids_and_waits(fake_session_factory):
    factory, created = fake_session_factory
    states = iter([FakeResponse(payload={"status": "completed", "result": {"ok": True}})])
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/zotero/items/ingest"): FakeResponse(payload={"status": "running"}),
            ("GET", "http://127.0.0.1:8000/api/ingest/status"): lambda **kwargs: next(states),
        }
    )

    result = runner.invoke(ra.app, ["--json", "zotero-ingest", "PID1", "PID2", "--reingest", "--poll-interval", "0.2"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "completed"
    assert created[0].calls[0]["json"] == {"zotero_persistent_ids": ["PID1", "PID2"], "reingest": True}


def test_query_posts_expected_payload(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/query"): FakeResponse(payload={"status": "completed", "result": {"ok": True}}),
        }
    )

    result = runner.invoke(
        ra.app,
        ["--json", "query", "hunter gatherer mobility", "--limit", "5", "--limit-scope", "chunks", "--chunks-per-paper", "2", "--no-wait"],
    )
    assert result.exit_code == 0, result.stdout
    post_call = created[0].calls[0]
    assert post_call["json"] == {
        "query": "hunter gatherer mobility",
        "limit": 5,
        "limit_scope": "chunks",
        "chunks_per_paper": 2,
        "score_threshold": None,
    }


def test_ask_uses_fixed_top_n_override_when_requested(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/ask"): FakeResponse(payload={"ok": True, "answer": "Grounded answer"}),
        }
    )

    result = runner.invoke(ra.app, ["--json", "ask", "What changed?", "--rag-results", "4", "--no-enforce-citations", "--no-preprocess-search"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["answer"] == "Grounded answer"
    assert created[0].calls[0]["json"] == {
        "question": "What changed?",
        "rag_results": 4,
        "score_threshold": ra.DEFAULT_ASK_SCORE_THRESHOLD,
        "retrieval_pool": ra.DEFAULT_ASK_RETRIEVAL_POOL,
        "enforce_citations": False,
        "preprocess_search": False,
    }


def test_ask_defaults_to_score_threshold_mode(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/ask"): FakeResponse(payload={"ok": True, "answer": "Grounded answer"}),
        }
    )

    result = runner.invoke(ra.app, ["--json", "ask", "What changed?"])
    assert result.exit_code == 0, result.stdout
    assert created[0].calls[0]["json"] == {
        "question": "What changed?",
        "score_threshold": ra.DEFAULT_ASK_SCORE_THRESHOLD,
        "retrieval_pool": ra.DEFAULT_ASK_RETRIEVAL_POOL,
        "enforce_citations": True,
        "preprocess_search": True,
    }


def test_query_human_output_reports_stage_changes_without_duplicate_running_lines(fake_session_factory):
    factory, _ = fake_session_factory
    states = iter(
        [
            FakeResponse(payload={"status": "running", "stage": "queued", "request_id": "job-7"}),
            FakeResponse(payload={"status": "running", "stage": "queued", "request_id": "job-7"}),
            FakeResponse(payload={"status": "running", "stage": "embedding", "completed": 1, "total": 3, "request_id": "job-7"}),
            FakeResponse(payload={"status": "running", "stage": "embedding", "completed": 1, "total": 3, "request_id": "job-7"}),
            FakeResponse(payload={"status": "completed", "result": {"ok": True}}),
        ]
    )
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/query"): FakeResponse(payload={"status": "running", "request_id": "job-7", "stage": "queued"}),
            ("GET", "http://127.0.0.1:8000/api/query/status"): lambda **kwargs: next(states),
        }
    )

    result = runner.invoke(ra.app, ["query", "--poll-interval", "0.2", "mobility"])
    assert result.exit_code == 0, result.stdout
    assert 'Started query: query | status=running | stage=queued | request_id=job-7' in result.stderr
    assert result.stderr.count('query | status=running | stage=queued | request_id=job-7') == 1
    assert 'query | status=running | stage=embedding | progress=1/3 | request_id=job-7' in result.stderr
    assert result.stderr.count('query | status=running | stage=embedding | progress=1/3 | request_id=job-7') == 1
    assert 'query | status=completed' in result.stderr
    assert json.loads(result.stdout)["status"] == "completed"


def test_async_progress_reporter_stays_quiet_on_tty(monkeypatch):
    notes = []
    cli = ra.CLIContext(base_url="http://127.0.0.1:8000", timeout=ra.DEFAULT_TIMEOUT, json_output=False)
    monkeypatch.setattr(ra.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(cli, "note", notes.append)
    reporter = ra.AsyncProgressReporter(cli, "query")

    reporter.started({"status": "running", "stage": "queued", "request_id": "job-tty"})
    reporter.update({"status": "running", "stage": "embedding", "request_id": "job-tty"})

    assert notes == []


def test_query_json_output_stays_clean_without_progress_messages(fake_session_factory):
    factory, _ = fake_session_factory
    states = iter([FakeResponse(payload={"status": "completed", "result": {"ok": True}})])
    factory(
        {
            ("POST", "http://127.0.0.1:8000/api/query"): FakeResponse(payload={"status": "running", "request_id": "job-json", "stage": "queued"}),
            ("GET", "http://127.0.0.1:8000/api/query/status"): lambda **kwargs: next(states),
        }
    )

    result = runner.invoke(ra.app, ["--json", "query", "--poll-interval", "0.2", "mobility"])
    assert result.exit_code == 0, result.stdout
    assert result.stdout.strip().startswith("{")
    assert json.loads(result.stdout)["status"] == "completed"


def test_article_and_articles_commands_hit_expected_endpoints(fake_session_factory):
    factory, created = fake_session_factory
    factory(
        {
            ("GET", "http://127.0.0.1:8000/api/article/shaw2026"): FakeResponse(payload={"ok": True, "article": {"title": "Thinking-Fast"}}),
            ("POST", "http://127.0.0.1:8000/api/articles/by-citekeys"): FakeResponse(payload={"ok": True, "found_count": 2}),
        }
    )

    one = runner.invoke(ra.app, ["--json", "article", "shaw2026", "--chunk-limit", "5"])
    assert one.exit_code == 0, one.stdout
    assert created[0].calls[0]["params"] == {"chunk_limit": 5}

    many = runner.invoke(ra.app, ["--json", "articles", "a", "b", "--chunk-limit", "2"])
    assert many.exit_code == 0, many.stdout
    assert created[0].calls[1]["json"] == {"citekeys": ["a", "b"], "chunk_limit": 2}


def test_start_background_waits_for_health(monkeypatch, tmp_path: Path, fake_session_factory):
    factory, _ = fake_session_factory
    states = iter(
        [
            ra.CLIError("not up yet"),
            {"status": "ok", "stats": {"articles": 1}},
        ]
    )

    def health_then_ready(**kwargs):
        state = next(states)
        if isinstance(state, Exception):
            raise state
        return FakeResponse(payload=state)

    factory({("GET", "http://127.0.0.1:8000/api/health"): health_then_ready})

    class FakeProcess:
        pid = 4321

        def poll(self):
            return None

    popen_calls = []

    def fake_popen(command, cwd=None, env=None, stdout=None, stderr=None, start_new_session=None):
        popen_calls.append({"command": command, "cwd": cwd, "env": env, "stdout": stdout, "stderr": stderr, "start_new_session": start_new_session})
        return FakeProcess()

    monkeypatch.setattr(ra, "ROOT", tmp_path)
    monkeypatch.setattr(ra, "START_SCRIPT", tmp_path / "start.sh")
    (tmp_path / "start.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setattr(ra.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(ra.time, "sleep", lambda *_args, **_kwargs: None)

    result = runner.invoke(ra.app, ["--json", "start", "--wait", "--poll-interval", "0.2"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["ready"] is True
    assert payload["pid"] == 4321
    assert popen_calls[0]["command"][0] == "bash"


def test_api_token_is_forwarded_in_default_session(monkeypatch, fake_session_factory):
    factory, created = fake_session_factory
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    factory({
        ("GET", "http://127.0.0.1:8000/api/version"): FakeResponse(payload={"status": "ok"}),
        ("GET", "http://127.0.0.1:8000/api/health"): FakeResponse(payload={"status": "ok"}),
        ("GET", "http://127.0.0.1:8000/api/diagnostics"): FakeResponse(payload={"ok": True}),
        ("GET", "http://127.0.0.1:8000/api/sync/status"): FakeResponse(payload={"status": "idle"}),
        ("GET", "http://127.0.0.1:8000/api/ingest/status"): FakeResponse(payload={"status": "idle"}),
        ("GET", "http://127.0.0.1:8000/api/query/status"): FakeResponse(payload={"status": "idle"}),
    })

    result = runner.invoke(ra.app, ["status"])
    assert result.exit_code == 0, result.stdout
    assert created[0].headers["Authorization"] == "Bearer secret-token"


def test_scripts_ra_wrapper_delegates_to_packaged_entrypoint(monkeypatch):
    called = {}

    def fake_entrypoint():
        called["ok"] = True

    monkeypatch.setattr(ra, "entrypoint", fake_entrypoint)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts" / "ra.py"), run_name="__main__")
    assert called == {"ok": True}
    assert called == {"ok": True}
