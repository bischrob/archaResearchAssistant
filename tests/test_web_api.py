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

    start = client.post("/api/sync", json={"dry_run": True})
    assert start.status_code == 200
    assert start.json()["status"] == "running"

    stop = client.post("/api/sync/stop")
    assert stop.status_code == 200

    final = wait_for_status(client, "/api/sync/status")
    assert final["status"] in {"cancelled", "completed"}
    assert "request_id" in final


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


def test_query_validation_and_success(monkeypatch, client):
    bad = client.post("/api/query", json={"query": "   ", "limit": 5})
    assert bad.status_code == 400

    captured = {}

    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1):
        captured["query"] = query
        captured["limit"] = limit
        captured["limit_scope"] = limit_scope
        captured["chunks_per_paper"] = chunks_per_paper
        return [{"chunk_id": "c1", "combined_score": 1.0, "article_title": "A"}]

    monkeypatch.setattr(
        webmain,
        "contextual_retrieve",
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
    assert captured["chunks_per_paper"] == 1


def test_ask_endpoint_returns_answer_and_citations(monkeypatch, client):
    captured = {}

    def fake_retrieve(store, query, limit, limit_scope="chunks", chunks_per_paper=1):
        captured["query"] = query
        captured["limit"] = limit
        captured["limit_scope"] = limit_scope
        captured["chunks_per_paper"] = chunks_per_paper
        return [{"chunk_id": "c1", "article_title": "Paper A", "article_year": 2020}]

    monkeypatch.setattr(
        webmain,
        "contextual_retrieve",
        fake_retrieve,
    )
    monkeypatch.setattr(
        webmain,
        "preprocess_search_query",
        lambda question, model=None: f"{question} bischoff archaeology",
    )
    monkeypatch.setattr(
        webmain,
        "ask_openai_grounded",
        lambda question, rows, model=None, enforce_citations=True: {
            "model": model or "gpt-test",
            "answer": "Answer [C1]",
            "used_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "all_citations": [{"citation_id": "C1", "article_title": "Paper A"}],
            "citation_enforced": True,
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
    assert captured["query"] == "What is this? bischoff archaeology"
    assert captured["limit_scope"] == "chunks"
    assert captured["chunks_per_paper"] == 1


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
