from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j import GraphDatabase

from src.rag.config import Settings
from webapp import main as webmain


def _wait_for_terminal(client: TestClient, path: str, timeout_s: float = 90.0) -> dict:
    start = time.time()
    last = {}
    while time.time() - start < timeout_s:
        last = client.get(path).json()
        if last.get("status") in {"completed", "failed", "cancelled", "idle"}:
            return last
        time.sleep(0.2)
    return last


def _require_e2e_enabled() -> None:
    if os.getenv("RUN_E2E", "").strip() != "1":
        pytest.skip("Set RUN_E2E=1 to run live full-stack E2E tests.")


def _neo4j_reachable(settings: Settings) -> bool:
    try:
        driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        try:
            with driver.session() as session:
                session.run("RETURN 1 AS ok").single()
            return True
        finally:
            driver.close()
    except Exception:
        return False


def _delete_test_article(settings: Settings, *, article_id: str, citekey: str) -> None:
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        with driver.session() as session:
            session.run(
                """
                MATCH (a:Article)
                WHERE a.id = $article_id OR toLower(coalesce(a.citekey, '')) = toLower($citekey)
                DETACH DELETE a
                """,
                article_id=article_id,
                citekey=citekey,
            )
            # Keep graph tidy when temporary author nodes become orphaned.
            session.run("MATCH (p:Author) WHERE NOT (p)-[:WROTE]->(:Article) DETACH DELETE p")
    finally:
        driver.close()


def _make_pdf(path: Path) -> None:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "E2E test paper body.\nMethods and findings for integration testing.\nReferences\nSmith (2024) Example reference.",
    )
    doc.save(path)
    doc.close()


@pytest.mark.e2e
def test_fullstack_sync_ingest_query_and_article_lookup(monkeypatch, tmp_path: Path) -> None:
    _require_e2e_enabled()

    run_id = uuid.uuid4().hex[:10]
    article_id = f"e2e_fullstack_{run_id}"
    pdf_name = f"{article_id}.pdf"
    citekey = f"e2e{run_id}cite"

    pdf_root = tmp_path / "pdfs"
    pdf_root.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_root / pdf_name
    _make_pdf(pdf_path)

    paperpile_path = tmp_path / "Paperpile.e2e.json"
    paperpile_path.write_text(
        json.dumps(
            [
                {
                    "_id": f"pp-{run_id}",
                    "title": f"E2E Fullstack Paper {run_id}",
                    "year": 2024,
                    "doi": f"10.9999/e2e.{run_id}",
                    "citekey": citekey,
                    "author": [{"formatted": "E2E Tester"}],
                    "attachments": [{"filename": str(pdf_path)}],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("METADATA_BACKEND", "paperpile")
    monkeypatch.setenv("PAPERPILE_JSON", str(paperpile_path))
    monkeypatch.setenv("PDF_SOURCE_DIR", str(pdf_root))
    monkeypatch.setenv("METADATA_REQUIRE_MATCH", "1")
    monkeypatch.setenv("CITATION_PARSER", "heuristic")
    monkeypatch.setenv("ZIP_PDF_ENABLE", "0")
    monkeypatch.setenv("CHUNK_STRIP_PAGE_NOISE", "1")
    monkeypatch.setenv("CHUNK_SIZE_WORDS", "120")
    monkeypatch.setenv("CHUNK_OVERLAP_WORDS", "20")

    settings = Settings()
    if not _neo4j_reachable(settings):
        pytest.skip(
            f"Neo4j not reachable at {settings.neo4j_uri}. Start services and rerun with RUN_E2E=1."
        )

    _delete_test_article(settings, article_id=article_id, citekey=citekey)
    webmain.jobs = webmain.JobManager()
    client = TestClient(webmain.app)

    try:
        start = client.post(
            "/api/sync",
            json={
                "dry_run": False,
                "source_dir": str(pdf_root),
                "source_mode": "filesystem",
                "run_ingest": True,
                "ingest_skip_existing": True,
            },
        )
        assert start.status_code == 200, start.text
        assert start.json().get("status") == "running"

        final_sync = _wait_for_terminal(client, "/api/sync/status", timeout_s=120.0)
        assert final_sync.get("status") == "completed", final_sync
        result = final_sync.get("result") or {}
        assert result.get("ok") is True
        assert result.get("ingest_ran") is True
        ingest_summary = result.get("ingest_summary") or {}
        assert int(ingest_summary.get("ingested_articles") or 0) >= 1

        article_resp = client.get(f"/api/article/{citekey}", params={"chunk_limit": 2})
        assert article_resp.status_code == 200, article_resp.text
        article_payload = article_resp.json()
        assert article_payload.get("ok") is True
        article = article_payload.get("article") or {}
        assert (article.get("article_citekey") or "").lower() == citekey.lower()
        assert article.get("chunk_count", 0) >= 1

        query_resp = client.post(
            "/api/query",
            json={
                "query": f"Fullstack Paper {run_id}",
                "limit": 5,
                "limit_scope": "papers",
                "chunks_per_paper": 1,
            },
        )
        assert query_resp.status_code == 200, query_resp.text
        final_query = _wait_for_terminal(client, "/api/query/status", timeout_s=40.0)
        assert final_query.get("status") == "completed", final_query
        qresult = final_query.get("result") or {}
        qrows = qresult.get("results") or []
        assert qrows, qresult
        assert any((row.get("article_citekey") or "").lower() == citekey.lower() for row in qrows)
    finally:
        _delete_test_article(settings, article_id=article_id, citekey=citekey)
