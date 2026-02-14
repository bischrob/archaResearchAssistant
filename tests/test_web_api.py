import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.rag.pipeline import IngestSummary
from webapp import main as webmain


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webmain, "jobs", webmain.JobManager())
    return TestClient(webmain.app)


def wait_for_status(client: TestClient, path: str, timeout_s: float = 2.0) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        payload = client.get(path).json()
        if payload["status"] != "running":
            return payload
        time.sleep(0.05)
    return client.get(path).json()


def test_health_endpoint_returns_stats(monkeypatch, client):
    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def graph_stats(self):
            return {"articles": 1, "chunks": 2, "tokens": 3, "references": 4, "cites": 5}

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["stats"]["articles"] == 1


def test_sync_start_status_and_stop(monkeypatch, tmp_path: Path, client):
    script = tmp_path / "sync.sh"
    script.write_text("#!/usr/bin/env bash\nsleep 1\n")
    monkeypatch.setattr(webmain, "SYNC_SCRIPT", script)

    class FakePopen:
        def __init__(self, *args, **kwargs):
            self._done = False
            self._terminated = False
            self.returncode = None

        def poll(self):
            if self._terminated:
                return 143
            return None if not self._done else 0

        def terminate(self):
            self._terminated = True
            self.returncode = 143

        def wait(self, timeout=None):
            self.returncode = 143
            return 143

        def communicate(self):
            return ("sync out", "")

    monkeypatch.setattr(webmain.subprocess, "Popen", lambda *a, **k: FakePopen())

    start = client.post("/api/sync", json={"dry_run": True})
    assert start.status_code == 200
    assert start.json()["status"] == "running"

    stop = client.post("/api/sync/stop")
    assert stop.status_code == 200

    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] in {"cancelled", "completed"}


def test_ingest_endpoint_runs_non_destructive(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "a.pdf"
    p.write_text("x")

    monkeypatch.setattr(webmain, "choose_pdfs", lambda **kwargs: [p])
    captured = {}

    def fake_ingest_pdfs(**kwargs):
        captured.update(kwargs)
        return IngestSummary(
            ingested_articles=1,
            total_chunks=2,
            total_references=3,
            selected_pdfs=[str(p)],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)
    resp = client.post(
        "/api/ingest",
        json={"mode": "test3", "source_dir": "pdfs", "pdfs": [], "override_existing": False},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "completed"}

    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    assert final["result"]["summary"]["ingested_articles"] == 1
    assert captured["wipe"] is False
    assert captured["skip_existing"] is True


def test_ingest_endpoint_override_existing(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "a.pdf"
    p.write_text("x")

    monkeypatch.setattr(webmain, "choose_pdfs", lambda **kwargs: [p])
    captured = {}

    def fake_ingest_pdfs(**kwargs):
        captured.update(kwargs)
        return IngestSummary(
            ingested_articles=1,
            total_chunks=2,
            total_references=3,
            selected_pdfs=[str(p)],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)
    resp = client.post(
        "/api/ingest",
        json={"mode": "test3", "source_dir": "pdfs", "pdfs": [], "override_existing": True},
    )
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    assert captured["skip_existing"] is False


def test_ingest_status_failed(monkeypatch, client):
    monkeypatch.setattr(webmain, "choose_pdfs", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("bad ingest")))
    resp = client.post("/api/ingest", json={"mode": "all", "source_dir": "pdfs", "pdfs": [], "override_existing": False})
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "failed"
    assert "bad ingest" in final["error"]


def test_ingest_preview_endpoint(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "demo.pdf"
    p.write_text("x")
    monkeypatch.setattr(webmain, "choose_pdfs", lambda **kwargs: [p])

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def existing_article_ids(self):
            return {p.stem}

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)
    monkeypatch.setattr(
        webmain,
        "load_paperpile_index",
        lambda _path: {p.name.lower(): {"title": "Demo Title", "year": 2024, "authors": ["Author A"]}},
    )

    resp = client.post(
        "/api/ingest/preview",
        json={"mode": "custom", "source_dir": "pdfs", "pdfs": [str(p)], "override_existing": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["summary"]["total_resolved"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["file"] == p.name
    assert data["rows"][0]["metadata_found"] is True
    assert data["rows"][0]["title"] == "Demo Title"


def test_query_validation_and_success(monkeypatch, client):
    bad = client.post("/api/query", json={"query": "   ", "limit": 5})
    assert bad.status_code == 400

    monkeypatch.setattr(
        webmain,
        "contextual_retrieve",
        lambda store, query, limit: [{"chunk_id": "c1", "combined_score": 1.0, "article_title": "A"}],
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    ok = client.post("/api/query", json={"query": "chronology", "limit": 5})
    assert ok.status_code == 200
    final = wait_for_status(client, "/api/query/status")
    assert final["status"] == "completed"
    assert len(final["result"]["results"]) == 1
