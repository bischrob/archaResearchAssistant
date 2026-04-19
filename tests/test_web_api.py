import time
import threading
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


def test_zotero_items_search_runtime_errors_return_json_detail(monkeypatch, client):
    class FakeSettings:
        zotero_db_path = ""
        zotero_storage_root = ""

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(
        webmain,
        "_browse_zotero_pdf_items",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Zotero DB not found: /missing/zotero.sqlite")),
    )

    resp = client.post("/api/zotero/items/search", json={"query": "", "limit": 10, "available_only": True})
    assert resp.status_code == 400
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "Zotero DB not found: /missing/zotero.sqlite"}


def test_zotero_items_search_unhandled_errors_return_json_detail(monkeypatch, client):
    class FakeSettings:
        zotero_db_path = "configured"
        zotero_storage_root = "configured"

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(
        webmain,
        "_browse_zotero_pdf_items",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("resolver exploded")),
    )

    error_client = TestClient(webmain.app, raise_server_exceptions=False)
    resp = error_client.post("/api/zotero/items/search", json={"query": "", "limit": 10, "available_only": True})
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.json() == {"detail": "resolver exploded"}


def test_sync_start_status_and_stop(monkeypatch, tmp_path: Path, client):
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    (pdf_root / "a.pdf").write_bytes(b"%PDF-1.7\n")

    class FakeSettings:
        pdf_source_dir = str(pdf_root)
        metadata_backend = "paperpile"
        paperpile_json = "Paperpile.json"
        zotero_db_path = ""
        zip_pdf_cache_dir = str(tmp_path / "zip_cache")
        zip_pdf_enable = False

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "load_paperpile_index", lambda _path: {"a.pdf": {"title": "A"}})
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        webmain,
        "find_metadata_for_pdf",
        lambda *args, **kwargs: (started.set() or release.wait(1) or None),
    )

    start = client.post("/api/sync", json={"dry_run": True, "source_mode": "filesystem"})
    assert start.status_code == 200
    assert start.json()["status"] == "running"
    assert started.wait(1.0)

    stop = client.post("/api/sync/stop")
    assert stop.status_code == 200
    stop_payload = stop.json()
    assert stop_payload["stop_state"] == "accepted"
    assert stop_payload["cancel_requested"] is True
    assert stop_payload["lifecycle_state"] in {"running", "cancelling"}
    release.set()

    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] in {"cancelled", "completed"}
    assert final["terminal_reason"] in {"cancelled", "completed"}
    assert "request_id" in final


def test_sync_stop_reports_noop_when_idle(client):
    resp = client.post("/api/sync/stop")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "idle"
    assert payload["lifecycle_state"] == "idle"
    assert payload["stop_state"] == "noop_idle"
    assert payload["cancel_requested"] is False


@pytest.mark.parametrize(
    ("source_mode", "run_ingest", "metadata_backend"),
    [
        ("filesystem", False, "paperpile"),
        ("zotero_db", True, "zotero"),
    ],
)
def test_sync_source_modes_and_run_ingest(monkeypatch, tmp_path: Path, client, source_mode, run_ingest, metadata_backend):
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    pdf1 = pdf_root / "one.pdf"
    pdf2 = pdf_root / "two.pdf"
    pdf1.write_bytes(b"%PDF-1.7\n")
    pdf2.write_bytes(b"%PDF-1.7\n")

    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    zotero_storage = tmp_path / "storage"
    zotero_storage.mkdir()

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "pdf_source_dir": str(pdf_root),
            "metadata_backend": metadata_backend,
            "paperpile_json": str(tmp_path / "Paperpile.json"),
            "zotero_db_path": str(zotero_db),
            "zotero_storage_root": str(zotero_storage),
            "zip_pdf_cache_dir": str(tmp_path / "zip_cache"),
            "zip_pdf_enable": False,
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "_load_metadata_index_for_settings", lambda settings: SimpleNamespace(backend=metadata_backend))

    if source_mode == "filesystem":
        def fake_collect_source_pdfs(*, source_root, cache_root, include_zip, progress_cb=None):
            assert source_root == pdf_root
            return [pdf1, pdf2], {"source_mode": "filesystem", "files": 2}

        monkeypatch.setattr(webmain, "collect_source_pdfs", fake_collect_source_pdfs)

        def fake_load_zotero_entries(*args, **kwargs):
            raise AssertionError("load_zotero_entries should not be called for filesystem mode")

        monkeypatch.setattr(webmain, "load_zotero_entries", fake_load_zotero_entries)
    else:
        def fake_collect_source_pdfs(*args, **kwargs):
            raise AssertionError("collect_source_pdfs should not be called for zotero_db mode")

        monkeypatch.setattr(webmain, "collect_source_pdfs", fake_collect_source_pdfs)

        def fake_load_zotero_entries(db_path, storage_root):
            assert Path(db_path) == zotero_db
            assert storage_root == str(zotero_storage)
            return [
                {"attachment_path": str(pdf1)},
                {"attachment_path": str(pdf2)},
            ]

        monkeypatch.setattr(webmain, "load_zotero_entries", fake_load_zotero_entries)

    monkeypatch.setattr(
        webmain,
        "find_metadata_for_pdf",
        lambda index, filename, path_hint=None: {"title": filename} if filename in {pdf1.name, pdf2.name} else None,
    )

    ingest_calls = []

    def fake_ingest_pdfs(**kwargs):
        ingest_calls.append(kwargs)
        selected = kwargs["selected_pdfs"]
        return IngestSummary(
            ingested_articles=len(selected),
            total_chunks=len(selected) * 2,
            total_references=len(selected),
            selected_pdfs=[str(p) for p in selected],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)

    resp = client.post(
        "/api/sync",
        json={
            "dry_run": False,
            "source_dir": str(pdf_root),
            "source_mode": source_mode,
            "run_ingest": run_ingest,
            "ingest_skip_existing": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] == "completed"
    assert final["lifecycle_state"] == "completed"
    assert final["terminal_reason"] == "completed"
    assert final["result"]["source_mode"] == source_mode
    assert final["result"]["pdfs_total"] == 2
    assert final["result"]["ingest_ran"] is run_ingest
    if run_ingest:
        assert len(ingest_calls) == 1
        assert ingest_calls[0]["skip_existing"] is True
        assert final["result"]["ingest_summary"]["ingested_articles"] == 2
    else:
        assert ingest_calls == []
        assert final["result"]["ingest_summary"] is None


def test_sync_zero_pdf_terminal_completion(monkeypatch, tmp_path: Path, client):
    pdf_root = tmp_path / "empty"
    pdf_root.mkdir()

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "pdf_source_dir": str(pdf_root),
            "metadata_backend": "paperpile",
            "paperpile_json": str(tmp_path / "Paperpile.json"),
            "zotero_db_path": "",
            "zotero_storage_root": "",
            "zip_pdf_cache_dir": str(tmp_path / "zip_cache"),
            "zip_pdf_enable": False,
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "_load_metadata_index_for_settings", lambda settings: SimpleNamespace(backend="paperpile"))

    def fake_collect_source_pdfs(*, source_root, cache_root, include_zip, progress_cb=None):
        assert source_root == pdf_root
        return [], {"source_mode": "filesystem", "files": 0}

    monkeypatch.setattr(webmain, "collect_source_pdfs", fake_collect_source_pdfs)

    def fail_find_metadata(*args, **kwargs):
        raise AssertionError("find_metadata_for_pdf should not be called when no PDFs are discovered")

    monkeypatch.setattr(webmain, "find_metadata_for_pdf", fail_find_metadata)
    monkeypatch.setattr(webmain, "ingest_pdfs", lambda **kwargs: (_ for _ in ()).throw(AssertionError("ingest should not run")))

    resp = client.post(
        "/api/sync",
        json={"dry_run": False, "source_dir": str(pdf_root), "source_mode": "filesystem", "run_ingest": True},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"

    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] == "completed"
    assert final["lifecycle_state"] == "completed"
    assert final["terminal_reason"] == "completed"
    assert final["progress_percent"] == 100.0
    assert final["progress_message"] == "Sync complete (no PDFs found)"
    assert final["result"]["pdfs_total"] == 0
    assert final["result"]["ingest_ran"] is False
    assert final["result"]["ingest_summary"] is None


def test_sync_stop_transitions_through_cancelling(monkeypatch, tmp_path: Path, client):
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    pdf = pdf_root / "cancel-me.pdf"
    pdf.write_bytes(b"%PDF-1.7\n")

    started = threading.Event()
    release = threading.Event()

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "pdf_source_dir": str(pdf_root),
            "metadata_backend": "paperpile",
            "paperpile_json": str(tmp_path / "Paperpile.json"),
            "zotero_db_path": "",
            "zotero_storage_root": "",
            "zip_pdf_cache_dir": str(tmp_path / "zip_cache"),
            "zip_pdf_enable": False,
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "_load_metadata_index_for_settings", lambda settings: SimpleNamespace(backend="paperpile"))
    monkeypatch.setattr(webmain, "collect_source_pdfs", lambda **kwargs: ([pdf], {"source_mode": "filesystem", "files": 1}))
    monkeypatch.setattr(webmain, "find_metadata_for_pdf", lambda index, filename, path_hint=None: {"title": filename})

    def fake_ingest_pdfs(**kwargs):
        started.set()
        while not release.is_set():
            time.sleep(0.01)
        return IngestSummary(
            ingested_articles=1,
            total_chunks=1,
            total_references=1,
            selected_pdfs=[str(pdf)],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)

    start = client.post(
        "/api/sync",
        json={"dry_run": False, "source_dir": str(pdf_root), "source_mode": "filesystem", "run_ingest": True},
    )
    assert start.status_code == 200
    start_payload = start.json()
    assert start_payload["status"] == "running"

    assert started.wait(1.0)
    stop = client.post("/api/sync/stop")
    assert stop.status_code == 200
    stop_payload = stop.json()
    assert stop_payload["status"] == "running"
    assert stop_payload["lifecycle_state"] == "cancelling"
    assert stop_payload["stop_state"] == "accepted"
    assert stop_payload["cancel_requested"] is True

    release.set()
    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] == "cancelled"
    assert final["lifecycle_state"] == "cancelled"
    assert final["terminal_reason"] == "cancelled"
    assert final["request_id"] == start_payload["request_id"]


def test_sync_defaults_to_zotero_db_when_source_mode_omitted(monkeypatch, tmp_path: Path, client):
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    zotero_storage = tmp_path / "storage"
    zotero_storage.mkdir()

    class FakeSettings:
        pdf_source_dir = str(tmp_path / "pdfs")
        metadata_backend = "zotero"
        zotero_db_path = str(zotero_db)
        zotero_storage_root = str(zotero_storage)
        zotero_require_persistent_id = False
        neo4j_uri = "bolt://ignored"
        neo4j_user = "neo4j"
        neo4j_password = "password"
        embedding_model = "test"

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "load_zotero_entries", lambda *args, **kwargs: [])

    class FakeResolver:
        def __init__(self, settings):
            pass

        def resolve(self, row):
            raise AssertionError("resolver should not be used when there are no rows")

        def close(self):
            pass

    monkeypatch.setattr(webmain, "ZoteroAttachmentResolver", FakeResolver)

    resp = client.post("/api/sync", json={"dry_run": True, "run_ingest": False})
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] == "completed"
    assert final["result"]["source_mode"] == "zotero_db"


def test_ingest_endpoint_runs_non_destructive(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "a.pdf"
    p.write_text("x")

    choose_calls = []
    monkeypatch.setattr(
        webmain,
        "choose_pdfs",
        lambda **kwargs: (choose_calls.append(kwargs) or [p]),
    )
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
        json={"mode": "test3", "source_dir": "pdfs", "pdfs": [], "override_existing": False, "partial_count": 7},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in {"running", "completed"}

    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    assert final["request_id"]
    assert final["result"]["summary"]["ingested_articles"] == 1
    assert captured["wipe"] is False
    assert captured["skip_existing"] is True
    assert choose_calls[0]["partial_count"] == 7


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


def test_ingest_all_runs_in_batches(monkeypatch, tmp_path: Path, client):
    files = []
    for i in range(5):
        p = tmp_path / f"f{i}.pdf"
        p.write_text("x")
        files.append(p)

    monkeypatch.setattr(webmain, "choose_pdfs", lambda **kwargs: files)
    calls = {"n": 0}

    def fake_ingest_pdfs(**kwargs):
        calls["n"] += 1
        selected = kwargs["selected_pdfs"]
        return IngestSummary(
            ingested_articles=len(selected),
            total_chunks=len(selected) * 2,
            total_references=len(selected),
            selected_pdfs=[str(p) for p in selected],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)
    resp = client.post(
        "/api/ingest",
        json={"mode": "all", "source_dir": "pdfs", "pdfs": [], "override_existing": False, "partial_count": 2},
    )
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    summary = final["result"]["summary"]
    assert summary["batch_total"] == 3
    assert len(summary["batch_results"]) == 3
    assert calls["n"] == 3
    assert summary["ingested_articles"] == 5


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
    monkeypatch.setenv("METADATA_BACKEND", "paperpile")
    choose_calls = []
    monkeypatch.setattr(
        webmain,
        "choose_pdfs",
        lambda **kwargs: (choose_calls.append(kwargs) or [p]),
    )

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
        json={"mode": "custom", "source_dir": "pdfs", "pdfs": [str(p)], "override_existing": False, "partial_count": 9},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["summary"]["total_resolved"] == 1
    assert len(data["rows"]) == 1
    assert data["rows"][0]["file"] == p.name
    assert data["rows"][0]["metadata_found"] is True
    assert data["rows"][0]["title"] == "Demo Title"
    assert choose_calls[0]["skip_existing"] is True
    assert choose_calls[0]["partial_count"] == 9


def test_ingest_endpoint_defaults_to_zotero_db_source_mode(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "a.pdf"
    p.write_text("x")

    choose_calls = []
    monkeypatch.setattr(
        webmain,
        "choose_pdfs",
        lambda **kwargs: (choose_calls.append(kwargs) or [p]),
    )
    monkeypatch.setattr(
        webmain,
        "ingest_pdfs",
        lambda **kwargs: IngestSummary(
            ingested_articles=1,
            total_chunks=1,
            total_references=0,
            selected_pdfs=[str(p)],
            skipped_existing_pdfs=[],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        ),
    )

    resp = client.post(
        "/api/ingest",
        json={"mode": "test3", "source_dir": "pdfs", "pdfs": [], "override_existing": False},
    )
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    assert choose_calls[0]["source_mode"] == "zotero_db"


def test_ingest_preview_defaults_to_zotero_db_source_mode(monkeypatch, tmp_path: Path, client):
    p = tmp_path / "demo.pdf"
    p.write_text("x")
    choose_calls = []
    monkeypatch.setattr(
        webmain,
        "choose_pdfs",
        lambda **kwargs: (choose_calls.append(kwargs) or [p]),
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def existing_article_ids(self):
            return set()

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)
    monkeypatch.setattr(webmain, "_load_metadata_index_for_settings", lambda _settings: {})
    monkeypatch.setattr(webmain, "find_metadata_for_pdf", lambda *args, **kwargs: None)

    resp = client.post(
        "/api/ingest/preview",
        json={"mode": "custom", "source_dir": "pdfs", "pdfs": [str(p)], "override_existing": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert [call["source_mode"] for call in choose_calls] == ["zotero_db", "zotero_db"]


def test_zotero_items_search_returns_available_pdf_rows(monkeypatch, tmp_path: Path, client):
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    storage = tmp_path / "storage"
    storage.mkdir()
    pdf_path = tmp_path / "available.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "zotero_db_path": str(zotero_db),
            "zotero_storage_root": str(storage),
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def existing_identity_hits(self, **kwargs):
            assert kwargs["zotero_persistent_ids"] == {"1:AAA"}
            return {"zotero_persistent_id": {"1:AAA"}}

        def close(self):
            pass

    resolutions = {
        "1:AAA": SimpleNamespace(
            path=pdf_path,
            resolver="local_storage",
            issue_code="ok",
            detail="",
            acquisition_source="zotero_storage_local",
            provenance={"resolver": "local_storage", "local_path": str(pdf_path)},
        ),
        "1:BBB": SimpleNamespace(
            path=None,
            resolver="local_storage",
            issue_code="zotero_storage_missing_local",
            detail="storage:missing.pdf",
            acquisition_source="unresolved",
            provenance={"resolver": "local_storage", "issue_code": "zotero_storage_missing_local"},
        ),
    }

    class FakeResolver:
        def __init__(self, settings):
            pass

        def resolve(self, row):
            return resolutions[row["zotero_persistent_id"]]

        def close(self):
            pass

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(
        webmain,
        "load_zotero_entries",
        lambda *args, **kwargs: [
            {"title": "Alpha Paper", "authors": ["Ada"], "doi": "10.1/a", "zotero_persistent_id": "1:AAA", "zotero_item_key": "AAA", "zotero_attachment_key": "ATT1"},
            {"title": "Beta Paper", "authors": ["Bob"], "doi": "10.1/b", "zotero_persistent_id": "1:BBB", "zotero_item_key": "BBB", "zotero_attachment_key": "ATT2"},
        ],
    )
    monkeypatch.setattr(webmain, "ZoteroAttachmentResolver", FakeResolver)
    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/zotero/items/search", json={"query": "alpha", "limit": 10, "available_only": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["total"] == 1
    assert len(data["items"]) == 1
    row = data["items"][0]
    assert row["zotero_persistent_id"] == "1:AAA"
    assert row["available"] is True
    assert row["exists_in_graph"] is True
    assert row["resolver"] == "local_storage"
    assert row["acquisition_source"] == "zotero_storage_local"


def test_zotero_items_search_filters_before_resolution(monkeypatch, tmp_path: Path, client):
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    storage = tmp_path / "storage"
    storage.mkdir()

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "zotero_db_path": str(zotero_db),
            "zotero_storage_root": str(storage),
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def existing_identity_hits(self, **kwargs):
            assert kwargs["zotero_persistent_ids"] == {"1:AAA"}
            return {"zotero_persistent_id": set()}

        def close(self):
            pass

    resolve_calls: list[str] = []

    class FakeResolver:
        def __init__(self, settings):
            pass

        def resolve(self, row):
            pid = row["zotero_persistent_id"]
            resolve_calls.append(pid)
            if pid == "1:BBB":
                raise AssertionError("non-matching row should not be resolved")
            return SimpleNamespace(
                path=tmp_path / "alpha.pdf",
                resolver="local_storage",
                issue_code="ok",
                detail="",
                acquisition_source="zotero_storage_local",
                provenance={"resolver": "local_storage"},
            )

        def close(self):
            pass

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(
        webmain,
        "load_zotero_entries",
        lambda *args, **kwargs: [
            {"title": "Alpha Paper", "authors": ["Ada"], "doi": "10.1/a", "journal": None, "publisher": None, "zotero_persistent_id": "1:AAA", "zotero_item_key": "AAA", "zotero_attachment_key": "ATT1", "attachment_path_raw": "storage:a.pdf", "attachment_path": str(tmp_path / "alpha.pdf")},
            {"title": "Beta Paper", "authors": ["Bob"], "doi": "10.1/b", "journal": None, "publisher": None, "zotero_persistent_id": "1:BBB", "zotero_item_key": "BBB", "zotero_attachment_key": "ATT2", "attachment_path_raw": "storage:b.pdf", "attachment_path": str(tmp_path / "beta.pdf")},
        ],
    )
    monkeypatch.setattr(webmain, "ZoteroAttachmentResolver", FakeResolver)
    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/zotero/items/search", json={"query": "alpha", "limit": 10, "available_only": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert resolve_calls == ["1:AAA"]


@pytest.mark.parametrize("reingest,expected_skip_existing", [(False, True), (True, False)])
def test_zotero_items_ingest_uses_selected_persistent_ids(monkeypatch, tmp_path: Path, client, reingest, expected_skip_existing):
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    storage = tmp_path / "storage"
    storage.mkdir()
    pdf_path = tmp_path / "selected.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")

    FakeSettings = type(
        "FakeSettings",
        (),
        {
            "zotero_db_path": str(zotero_db),
            "zotero_storage_root": str(storage),
            "neo4j_uri": "bolt://example:7687",
            "neo4j_user": "neo4j",
            "neo4j_password": "pass",
            "embedding_model": "model",
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def existing_identity_hits(self, **kwargs):
            return {"zotero_persistent_id": {"1:AAA"}}

        def close(self):
            pass

    class FakeResolver:
        def __init__(self, settings):
            pass

        def resolve(self, row):
            return SimpleNamespace(
                path=pdf_path,
                resolver="local_storage",
                issue_code="ok",
                detail="",
                acquisition_source="zotero_storage_local",
                provenance={"resolver": "local_storage", "local_path": str(pdf_path)},
            )

        def close(self):
            pass

    ingest_calls = []

    def fake_ingest_pdfs(**kwargs):
        ingest_calls.append(kwargs)
        return IngestSummary(
            ingested_articles=1,
            total_chunks=2,
            total_references=1,
            selected_pdfs=[str(pdf_path)],
            skipped_existing_pdfs=[] if reingest else [str(pdf_path)],
            skipped_no_metadata_pdfs=[],
            failed_pdfs=[],
        )

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(
        webmain,
        "load_zotero_entries",
        lambda *args, **kwargs: [
            {"title": "Alpha Paper", "authors": ["Ada"], "doi": "10.1/a", "zotero_persistent_id": "1:AAA", "zotero_item_key": "AAA", "zotero_attachment_key": "ATT1"},
        ],
    )
    monkeypatch.setattr(webmain, "ZoteroAttachmentResolver", FakeResolver)
    monkeypatch.setattr(webmain, "GraphStore", FakeStore)
    monkeypatch.setattr(webmain, "ingest_pdfs", fake_ingest_pdfs)

    resp = client.post("/api/zotero/items/ingest", json={"zotero_persistent_ids": ["1:AAA"], "reingest": reingest})
    assert resp.status_code == 200
    final = wait_for_status(client, "/api/ingest/status")
    assert final["status"] == "completed"
    assert final["result"]["source_mode"] == "zotero_db"
    assert final["result"]["reingest"] is reingest
    assert final["result"]["selected_items"][0]["zotero_persistent_id"] == "1:AAA"
    assert ingest_calls[0]["skip_existing"] is expected_skip_existing
    assert ingest_calls[0]["selected_pdfs"] == [pdf_path]



def test_query_validation_and_success(monkeypatch, client):
    bad = client.post("/api/query", json={"query": "   ", "limit": 5})
    assert bad.status_code == 400

    captured = {}

    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1, score_threshold=None):
        captured["query"] = query
        captured["limit"] = limit
        captured["limit_scope"] = limit_scope
        captured["chunks_per_paper"] = chunks_per_paper
        captured["score_threshold"] = score_threshold
        return [{"chunk_id": "c1", "combined_score": 1.0, "article_title": "A"}]

    monkeypatch.setattr(
        webmain,
        "graphrag_retrieve",
        fake_retrieve,
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    ok = client.post("/api/query", json={"query": "chronology"})
    assert ok.status_code == 200
    final = wait_for_status(client, "/api/query/status")
    assert final["status"] == "completed"
    assert len(final["result"]["results"]) == 1
    assert captured["query"] == "chronology"
    assert captured["limit"] == 20
    assert captured["limit_scope"] == "papers"
    assert captured["chunks_per_paper"] == 8
    assert captured["score_threshold"] is None


def test_ask_endpoint_returns_answer_and_citations(monkeypatch, client):
    captured = {}

    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1, score_threshold=None):
        captured["query"] = query
        captured["limit"] = limit
        captured["limit_scope"] = limit_scope
        captured["chunks_per_paper"] = chunks_per_paper
        captured["score_threshold"] = score_threshold
        return [{"chunk_id": "c1", "article_title": "Paper A", "article_year": 2020}]

    monkeypatch.setattr(
        webmain,
        "graphrag_retrieve",
        fake_retrieve,
    )
    monkeypatch.setattr(
        webmain,
        "preprocess_search_query",
        lambda question, model=None: f"{question} bischoff archaeology",
    )
    monkeypatch.setattr(
        webmain,
        "ask_grounded",
        lambda question, rows, model=None, enforce_citations=True: {
            "model": model or "gpt-test",
            "answer": "Answer [C1]",
            "used_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "all_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "succeeded",
            "fallback_reason": None,
            "evidence_snippets": ["[C1] supporting text"],
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/ask", json={"question": "What is this?", "rag_results": 3, "model": "gpt-test"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["answer"] == "Answer [C1]"
    assert len(data["used_citations"]) == 1
    assert data["search_query_used"] == "What is this? bischoff archaeology"
    assert data["query_preprocess"]["method"] == "llm_rewrite"
    assert data["answer_method"] == "deterministic_fallback"
    assert data["synthesis_status"] == "succeeded"
    assert data["fallback_reason"] is None
    assert data["evidence_snippets"] == ["[C1] supporting text"]
    assert captured["query"] == "What is this? bischoff archaeology"
    assert captured["limit_scope"] == "chunks"
    assert captured["chunks_per_paper"] == 1
    assert captured["limit"] == 3
    assert captured["score_threshold"] is None
    assert data["retrieval_mode"] == "fixed_top_n"
    assert data["retrieval_pool"] == 3
    assert data["score_threshold"] is None


def test_ask_endpoint_surfaces_explicit_fallback_without_raw_chunk_answer(client, monkeypatch):
    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1, score_threshold=None):
        return [{"chunk_id": "c1", "chunk_text": "Raw retrieved chunk text", "article_title": "Paper A", "article_year": 2020}]

    monkeypatch.setattr(webmain, "graphrag_retrieve", fake_retrieve)
    monkeypatch.setattr(webmain, "preprocess_search_query", lambda question, model=None: question)
    monkeypatch.setattr(
        webmain,
        "ask_grounded",
        lambda question, rows, model=None, enforce_citations=True: {
            "answer": "Unable to produce a synthesized grounded answer from the retrieved context. See the returned citations and evidence snippets for the supporting passages.",
            "used_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "all_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "failed",
            "fallback_reason": "invalid_agent_response",
            "evidence_snippets": ["[C1] Raw retrieved chunk text"],
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/ask", json={"question": "What projectile points are found in Arizona?", "rag_results": 1})
    assert resp.status_code == 200
    data = resp.json()
    assert data["answer_method"] == "deterministic_fallback"
    assert data["synthesis_status"] == "failed"
    assert data["fallback_reason"] == "invalid_agent_response"
    assert data["answer"].startswith("Unable to produce a synthesized grounded answer")
    assert "Raw retrieved chunk text" not in data["answer"]
    assert data["evidence_snippets"] == ["[C1] Raw retrieved chunk text"]


def test_ask_endpoint_returns_relevance_filtering_metadata(client, monkeypatch):
    monkeypatch.setattr(webmain, "graphrag_retrieve", lambda *args, **kwargs: [
        {"chunk_id": "c1", "chunk_text": "Binford argued for archaeology as anthropology.", "article_title": "Paper A", "article_year": 1962},
        {"chunk_id": "c2", "chunk_text": "Unrelated marine isotope chemistry.", "article_title": "Paper B", "article_year": 2021},
    ])
    monkeypatch.setattr(webmain, "preprocess_search_query", lambda question, model=None: question)
    monkeypatch.setattr(
        webmain,
        "ask_grounded",
        lambda question, rows, model=None, enforce_citations=True: {
            "answer": "Binford framed archaeology as anthropology [C1]",
            "used_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "relevant_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "excluded_citations": [{"citation_id": "C2", "article_title": "Paper B"}],
            "all_citations": [{"citation_id": "C1", "article_title": "Paper A"}, {"citation_id": "C2", "article_title": "Paper B"}],
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "succeeded",
            "fallback_reason": None,
            "evidence_snippets": ["[C1] Binford argued for archaeology as anthropology."],
            "relevance_summary": "Used 1 of 2 retrieved results after relevance filtering.",
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/ask", json={"question": "What did Binford argue?", "rag_results": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert data["relevance_summary"] == "Used 1 of 2 retrieved results after relevance filtering."
    assert [c["citation_id"] for c in data["relevant_citations"]] == ["C1"]
    assert [c["citation_id"] for c in data["excluded_citations"]] == ["C2"]


def test_ask_endpoint_defaults_to_score_threshold_mode(monkeypatch, client):
    captured = {}

    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1, score_threshold=None):
        captured["limit"] = limit
        captured["score_threshold"] = score_threshold
        return [{"chunk_id": "c1", "article_title": "Paper A", "article_year": 2020, "rerank_score": 1.2}]

    monkeypatch.setattr(webmain, "graphrag_retrieve", fake_retrieve)
    monkeypatch.setattr(webmain, "preprocess_search_query", lambda question, model=None: question)
    monkeypatch.setattr(
        webmain,
        "ask_grounded",
        lambda question, rows, model=None, enforce_citations=True: {
            "answer": "Answer [C1]",
            "used_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "all_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "succeeded",
            "fallback_reason": None,
            "evidence_snippets": ["[C1] supporting text"],
        },
    )

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

    monkeypatch.setattr(webmain, "GraphStore", FakeStore)

    resp = client.post("/api/ask", json={"question": "What is this?"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "score_threshold"
    assert data["retrieval_pool"] == webmain.DEFAULT_ASK_RETRIEVAL_POOL
    assert data["score_threshold"] == webmain.DEFAULT_ASK_SCORE_THRESHOLD
    assert captured["limit"] == webmain.DEFAULT_ASK_RETRIEVAL_POOL
    assert captured["score_threshold"] == webmain.DEFAULT_ASK_SCORE_THRESHOLD


def test_ask_export_markdown_and_csv(client):
    report = {
        "question": "Q?",
        "model": "gpt-test",
        "rag_results_count": 2,
        "answer": "A [C1]",
        "audit": {"risk_label": "low", "risk_score": 0.1},
        "used_citations": [
            {
                "citation_id": "C1",
                "article_title": "Paper A",
                "article_year": 2020,
                "authors": ["A A"],
                "citekey": "A2020-x",
                "doi": "10.1/x",
                "page_start": 1,
                "page_end": 2,
                "chunk_id": "ch1",
            }
        ],
    }
    md = client.post("/api/ask/export", json={"report": report, "format": "markdown"})
    assert md.status_code == 200
    assert "RAG Answer Report" in md.text
    assert "A [C1]" in md.text

    csv_resp = client.post("/api/ask/export", json={"report": report, "format": "csv"})
    assert csv_resp.status_code == 200
    assert "citation_id,article_title" in csv_resp.text
    assert "C1,Paper A" in csv_resp.text


def test_ask_export_pdf(client, monkeypatch):
    report = {
        "question": "Q?",
        "model": "gpt-test",
        "rag_results_count": 1,
        "answer": "A [C1]",
        "used_citations": [],
    }
    monkeypatch.setattr(webmain, "markdown_to_pdf_bytes", lambda _md: b"%PDF-1.7\nfake\n")
    resp = client.post("/api/ask/export", json={"report": report, "format": "pdf"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content.startswith(b"%PDF")


def test_diagnostics_endpoint_reports_pass(monkeypatch, tmp_path: Path, client):
    monkeypatch.chdir(tmp_path)
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    (pdf_root / "a.pdf").write_bytes(b"%PDF-1.7\n")
    (pdf_root / "b.pdf").write_bytes(b"%PDF-1.7\n")
    paperpile_path = tmp_path / "Paperpile.json"
    paperpile_path.write_text("[]", encoding="utf-8")
    sync_script = tmp_path / "sync.sh"
    sync_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(webmain, "SYNC_SCRIPT", sync_script)

    class FakeSettings:
        neo4j_uri = "bolt://example:7687"
        neo4j_user = "neo4j"
        neo4j_password = "pass"
        embedding_model = "model"
        metadata_backend = "paperpile"
        paperpile_json = str(paperpile_path)
        zotero_db_path = ""

    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass

        def graph_stats(self):
            return {"articles": 3, "chunks": 4, "tokens": 5, "references": 6, "cites": 7}

        def close(self):
            pass

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "GraphStore", FakeStore)
    monkeypatch.setattr(webmain, "load_paperpile_index", lambda _path: {"a.pdf": {"title": "A"}})
    monkeypatch.setattr(
        webmain,
        "find_metadata_for_pdf",
        lambda index, filename: index.get(filename.lower()),
    )

    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["details"]["pdfs_total"] == 2
    assert data["details"]["pdfs_with_metadata"] == 1
    assert data["details"]["neo4j_stats"]["articles"] == 3
    assert any(c["name"] == "neo4j_connectivity" and c["ok"] is True for c in data["checks"])


def test_diagnostics_endpoint_reports_neo4j_failure(monkeypatch, tmp_path: Path, client):
    monkeypatch.chdir(tmp_path)
    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir()
    (pdf_root / "a.pdf").write_bytes(b"%PDF-1.7\n")
    paperpile_path = tmp_path / "Paperpile.json"
    paperpile_path.write_text("[]", encoding="utf-8")
    sync_script = tmp_path / "sync.sh"
    sync_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(webmain, "SYNC_SCRIPT", sync_script)

    class FakeSettings:
        neo4j_uri = "bolt://example:7687"
        neo4j_user = "neo4j"
        neo4j_password = "pass"
        embedding_model = "model"
        metadata_backend = "paperpile"
        paperpile_json = str(paperpile_path)
        zotero_db_path = ""

    class FailingStore:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("neo4j down")

    monkeypatch.setattr(webmain, "Settings", FakeSettings)
    monkeypatch.setattr(webmain, "GraphStore", FailingStore)
    monkeypatch.setattr(webmain, "load_paperpile_index", lambda _path: {"a.pdf": {"title": "A"}})
    monkeypatch.setattr(
        webmain,
        "find_metadata_for_pdf",
        lambda index, filename: index.get(filename.lower()),
    )

    resp = client.get("/api/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert any(c["name"] == "neo4j_connectivity" and c["ok"] is False for c in data["checks"])


def test_api_bearer_token_is_optional_by_default(client):
    resp = client.get("/api/sync/status")
    assert resp.status_code == 200


def test_api_bearer_token_enforced_when_set(monkeypatch, client):
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")

    missing = client.get("/api/sync/status")
    assert missing.status_code == 401

    bad = client.get("/api/sync/status", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 403

    good = client.get("/api/sync/status", headers={"Authorization": "Bearer secret-token"})
    assert good.status_code == 200


@pytest.mark.parametrize(
    "method,path",
    [
        ("post", "/api/sync/stop"),
        ("get", "/api/sync/status"),
        ("post", "/api/ingest/stop"),
        ("get", "/api/ingest/status"),
        ("post", "/api/query/stop"),
        ("get", "/api/query/status"),
    ],
)
def test_job_endpoints_require_bearer_token_when_set(monkeypatch, client, method, path):
    monkeypatch.setenv("API_BEARER_TOKEN", "secret-token")
    request = getattr(client, method)
    missing = request(path)
    bad = request(path, headers={"Authorization": "Bearer wrong"})
    good = request(path, headers={"Authorization": "Bearer secret-token"})
    assert missing.status_code == 401
    assert bad.status_code == 403
    assert good.status_code == 200


def test_ask_endpoint_reports_usable_vs_excluded_rag_results(monkeypatch, client):
    class FakeStore:
        def __init__(self, *args, **kwargs):
            pass
        def close(self):
            pass

    monkeypatch.setattr(webmain, 'GraphStore', FakeStore)
    monkeypatch.setattr(
        webmain,
        'graphrag_retrieve',
        lambda *args, **kwargs: [
            {'chunk_id': 'c1', 'chunk_text': 'Hohokam projectile point typology in Arizona.', 'article_title': 'Hohokam Lithics', 'article_year': 2020},
            {'chunk_id': 'c2', 'chunk_text': 'General Hohokam irrigation systems.', 'article_title': 'Hohokam Water', 'article_year': 2019},
        ],
    )
    monkeypatch.setattr(
        webmain,
        'ask_grounded',
        lambda question, rows, model=None, enforce_citations=True: {
            'answer': 'Grounded answer [C1]',
            'citation_enforced': True,
            'method': 'deterministic_fallback',
            'synthesis_status': 'succeeded',
            'fallback_reason': None,
            'agent_error': None,
            'evidence_snippets': [],
            'relevance_summary': 'Used 1 of 1 retrieved results after hard relevance gating before synthesis.',
            'used_citations': [{'citation_id': 'C1'}],
            'relevant_citations': [{'citation_id': 'C1'}],
            'excluded_citations': [],
            'all_citations': [{'citation_id': 'C1'}],
            'model': None,
        },
    )

    resp = client.post('/api/ask', json={'question': 'Hohokam projectile points in Arizona', 'preprocess_search': False})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload['rag_results_count'] == 2
    assert payload['usable_rag_results_count'] == 1
    assert payload['excluded_rag_results_count'] == 1
    assert payload['usable_rag_results'][0]['chunk_id'] == 'c1'
    assert payload['excluded_rag_results'][0]['chunk_id'] == 'c2'
