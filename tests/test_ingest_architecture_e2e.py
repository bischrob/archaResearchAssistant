from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.pdf_processing import ArticleDoc, Chunk, Citation
from src.rag.pipeline import IngestSummary, choose_pdfs, ingest_pdfs
from src.rag.openclaw_structured_refs import SectionSpan, extract_structured_chunks_and_citations
from webapp import main as webmain


class _Resolver:
    def __init__(self, _settings, resolutions):
        self._resolutions = list(resolutions)

    def resolve(self, _row):
        return self._resolutions.pop(0)

    def close(self):
        return None


def test_choose_pdfs_zotero_first_requires_persistent_ids(monkeypatch, tmp_path: Path) -> None:
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")

    settings = Settings(
        metadata_backend="zotero",
        zotero_db_path=str(zotero_db),
        zotero_storage_root=str(tmp_path / "storage"),
        zotero_require_persistent_id=True,
    )

    monkeypatch.setattr(
        "src.rag.pipeline.load_zotero_entries",
        lambda *_args, **_kwargs: [{"attachment_path": str(tmp_path / 'paper.pdf'), "zotero_persistent_id": ""}],
    )

    with pytest.raises(ValueError, match="zotero_persistent_id"):
        choose_pdfs(settings=settings, source_mode="zotero_db", mode="all", skip_existing=False, require_metadata=False)


@pytest.mark.parametrize("fallback_used,method", [(False, "native_pdf"), (True, "native_pdf_plus_paddleocr_fallback")])
def test_ingest_pipeline_preserves_text_acquisition_provenance(monkeypatch, tmp_path: Path, fallback_used: bool, method: str) -> None:
    pdf_path = tmp_path / f"doc-{int(fallback_used)}.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")

    article = ArticleDoc(
        article_id=pdf_path.stem,
        title="Doc",
        normalized_title="doc",
        year=2024,
        author="Tester",
        authors=["Tester"],
        citekey="tester2024doc",
        paperpile_id=None,
        doi="10.1000/example",
        journal=None,
        publisher=None,
        source_path=str(pdf_path),
        text_acquisition_method=method,
        text_acquisition_fallback_used=fallback_used,
        text_quality_check_backend="heuristic_placeholder",
        native_text_malformed=fallback_used,
        native_text_malformed_reason="native_text_too_short" if fallback_used else None,
        native_text_char_count=42,
        paddleocr_text_path=str(tmp_path / "doc.txt") if fallback_used else None,
        ocr_engine="paddleocr" if fallback_used else None,
        ocr_model="PaddleOCR[classic]:lang=en,device=cpu" if fallback_used else None,
        ocr_version="3.0.0" if fallback_used else None,
        ocr_processed_at="2026-03-21T22:00:00Z" if fallback_used else None,
        ocr_quality_summary="native_reason=native_text_too_short" if fallback_used else None,
        chunks=[
            Chunk(
                chunk_id=f"{pdf_path.stem}::chunk::0",
                index=0,
                text="Body section tokens for integration coverage.",
                tokens=["body", "section", "tokens"],
                token_counts={"body": 1, "section": 1, "tokens": 1},
                page_start=1,
                page_end=1,
                section_type="body",
            )
        ],
        citations=[
            Citation(
                citation_id=f"{pdf_path.stem}::ref::0",
                raw_text="Smith 2024. Example reference.",
                year=2024,
                title_guess="Example reference",
                normalized_title="example reference",
                source="heuristic",
            )
        ],
    )

    captured = {}

    class _FakeStore:
        embedding_dimension = 3

        def __init__(self, *args, **kwargs):
            pass

        def setup_schema(self, vector_dimensions: int) -> None:
            captured["vector_dimensions"] = vector_dimensions

        def ingest_articles(self, articles, should_cancel=None, article_progress_callback=None) -> None:
            captured["articles"] = articles

        def close(self) -> None:
            return None

    monkeypatch.setattr("src.rag.pipeline._load_metadata_index_for_settings", lambda _settings: object())
    monkeypatch.setattr("src.rag.pipeline.find_metadata_for_pdf", lambda *_args, **_kwargs: {"title": "Doc"})
    monkeypatch.setattr("src.rag.pipeline._get_existing_identity_hits_for_candidates", lambda *_args, **_kwargs: {k: set() for k in ["article_ids", "doi", "zotero_persistent_id", "zotero_item_key", "zotero_attachment_key", "title_year_key", "title_year_key_normalized", "file_stem"]})
    monkeypatch.setattr("src.rag.pipeline._load_article_cached", lambda **_kwargs: article)
    monkeypatch.setattr("src.rag.pipeline.extract_keywords", lambda article, settings=None: ([], {"method": "test"}))
    monkeypatch.setattr("src.rag.pipeline.GraphStore", _FakeStore)

    summary = ingest_pdfs(selected_pdfs=[pdf_path], skip_existing=False, settings=Settings(metadata_backend="paperpile", metadata_require_match=False, citation_parser="heuristic"))

    assert isinstance(summary, IngestSummary)
    assert summary.ingested_articles == 1
    stored = captured["articles"][0]
    assert stored.text_acquisition_method == method
    assert stored.text_acquisition_fallback_used is fallback_used
    if fallback_used:
        assert stored.native_text_malformed is True
        assert "native_text_too_short" in (stored.ocr_quality_summary or "")


def test_structured_reference_extraction_writes_references_sidecar(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "segmented.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    settings = Settings()

    lines_with_page = [
        (1, "Introduction"),
        (1, "Body paragraph one for section-aware chunking."),
        (1, "References"),
        (1, "Smith, J. 2024. Example reference one."),
        (1, "Jones, A. 2023. Example reference two."),
    ]

    monkeypatch.setattr("src.rag.openclaw_structured_refs._extract_lines_with_page", lambda *args, **kwargs: lines_with_page)
    monkeypatch.setattr(
        "src.rag.openclaw_structured_refs.detect_section_plan_details",
        lambda lines, settings=None: (
            ["Introduction", "References"],
            [SectionSpan(start_line=0, end_line=1, kind="body"), SectionSpan(start_line=2, end_line=4, kind="references")],
            None,
        ),
    )
    monkeypatch.setattr(
        "src.rag.openclaw_structured_refs.parse_reference_strings_with_anystyle_docker",
        lambda reference_strings, **kwargs: [
            Citation(
                citation_id="segmented::ref::0",
                raw_text=reference_strings[0],
                year=2024,
                title_guess="Example reference one",
                normalized_title="example reference one",
                source="anystyle",
            )
        ],
    )

    result = extract_structured_chunks_and_citations(
        pdf_path=pdf_path,
        article_id="segmented",
        settings=settings,
        chunk_size_words=32,
        chunk_overlap_words=8,
        strip_page_noise=True,
    )

    assert result.sections
    assert any(section.kind == "references" for section in result.sections)
    assert result.chunks
    assert all(chunk.section_type == "body" for chunk in result.chunks)
    assert len(result.reference_strings) == 2
    sidecar = pdf_path.with_suffix(".references.txt")
    assert sidecar.exists()
    body = sidecar.read_text(encoding="utf-8")
    assert "Example reference one" in body
    assert "Example reference two" in body


def test_sync_zotero_mode_reports_attachment_resolver_provenance(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "resolved.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    zotero_db = tmp_path / "zotero.sqlite"
    zotero_db.write_text("stub", encoding="utf-8")
    storage = tmp_path / "storage"
    storage.mkdir()

    resolutions = [
        SimpleNamespace(path=pdf_path, resolver="attachment_path", issue_code="ok", detail=None),
        SimpleNamespace(path=None, resolver=None, issue_code="missing_attachment", detail="missing.pdf"),
    ]

    class _FakeSettings:
        pdf_source_dir = str(tmp_path)
        metadata_backend = "zotero"
        paperpile_json = str(tmp_path / "Paperpile.json")
        zotero_db_path = str(zotero_db)
        zotero_storage_root = str(storage)
        zip_pdf_cache_dir = str(tmp_path / "zip_cache")
        zip_pdf_enable = False
        neo4j_uri = "bolt://example:7687"
        neo4j_user = "neo4j"
        neo4j_password = "pass"
        embedding_model = "model"
        zotero_require_persistent_id = False
        metadata_require_match = False

    monkeypatch.setattr(webmain, "Settings", _FakeSettings)
    monkeypatch.setattr(webmain, "load_zotero_entries", lambda *_args, **_kwargs: [{"zotero_persistent_id": "p1"}, {"zotero_persistent_id": "p2"}])
    monkeypatch.setattr(webmain, "ZoteroAttachmentResolver", lambda settings: _Resolver(settings, resolutions))
    monkeypatch.setattr(webmain, "ingest_pdfs", lambda **kwargs: IngestSummary(ingested_articles=1, total_chunks=1, total_references=0, selected_pdfs=[str(pdf_path)], skipped_existing_pdfs=[], skipped_no_metadata_pdfs=[], failed_pdfs=[]))

    client = webmain.TestClient(webmain.app) if hasattr(webmain, "TestClient") else None
    if client is None:
        from fastapi.testclient import TestClient
        client = TestClient(webmain.app)

    webmain.jobs = webmain.JobManager()
    resp = client.post("/api/sync", json={"source_mode": "zotero_db", "run_ingest": False, "dry_run": True})
    assert resp.status_code == 200

    status = client.get("/api/sync/status").json()
    while status["status"] == "running":
        status = client.get("/api/sync/status").json()

    assert status["status"] == "completed"
    source_stats = status["result"]["source_stats"]
    assert source_stats["zotero_path_resolver_counts"] == {"attachment_path": 1}
    assert source_stats["zotero_path_issue_counts"] == {"missing_attachment": 1}
    assert source_stats["zotero_path_issue_samples"]["missing_attachment"] == ["missing.pdf"]


def test_reference_ingest_tx_replaces_article_scoped_reference_nodes(monkeypatch) -> None:
    from tests.test_neo4j_store import _FakeDriver, _FakeSentenceTransformer

    fake_driver = _FakeDriver()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)

    store = GraphStore("bolt://unused", "neo4j", "pass")
    try:
        article = ArticleDoc(
            article_id="versioned",
            title="Versioned",
            normalized_title="versioned",
            year=2024,
            author="Tester",
            authors=["Tester"],
            citekey=None,
            paperpile_id=None,
            doi=None,
            journal=None,
            publisher=None,
            source_path="/tmp/versioned.pdf",
            chunks=[],
            citations=[
                Citation(
                    citation_id="versioned::ref::0",
                    raw_text="Smith 2024. Version one.",
                    year=2024,
                    title_guess="Version one",
                    normalized_title="version one",
                    source="heuristic",
                )
            ],
        )
        store.ingest_articles([article])
    finally:
        store.close()

    session = fake_driver.sessions[0]
    cleanup = next(query for query in session.tx_queries if "OPTIONAL MATCH (a)-[:CITES_REFERENCE]->(r:Reference)" in query)
    assert "DETACH DELETE r" in cleanup
    reference_write = next(kwargs for query, kwargs in zip(session.tx_queries, session.tx_kwargs) if "MERGE (r:Reference {id: $id})" in query)
    assert reference_write["id"] == "versioned::ref::0"
    assert reference_write["source"] == "heuristic"
