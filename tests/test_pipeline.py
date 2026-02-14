from pathlib import Path

import pytest

from src.rag import pipeline
from src.rag.config import Settings
from src.rag.pdf_processing import ArticleDoc, Chunk


def _write_pdf_header(path: Path) -> None:
    path.write_bytes(b"%PDF-1.7\nfake")


def test_choose_pdfs_test3_prefers_readable_headers(tmp_path: Path) -> None:
    bad = tmp_path / "a.pdf"
    good1 = tmp_path / "b.pdf"
    good2 = tmp_path / "c.pdf"
    good3 = tmp_path / "d.pdf"
    bad.write_bytes(b"\x00\x00\x00\x00")
    _write_pdf_header(good1)
    _write_pdf_header(good2)
    _write_pdf_header(good3)

    selected = pipeline.choose_pdfs(mode="test3", source_dir=str(tmp_path), skip_existing=False, require_metadata=False)

    assert selected == [good1, good2, good3]


def test_choose_pdfs_all_includes_all_pdf_files(tmp_path: Path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    p1 = tmp_path / "z.pdf"
    p2 = sub / "a.pdf"
    p1.write_bytes(b"x")
    p2.write_bytes(b"y")

    selected = pipeline.choose_pdfs(mode="all", source_dir=str(tmp_path), skip_existing=False, require_metadata=False)

    assert selected == [p2, p1]


def test_choose_pdfs_custom_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        pipeline.choose_pdfs(
            mode="custom",
            explicit_pdfs=[str(tmp_path / "missing.pdf")],
            skip_existing=False,
            require_metadata=False,
        )


def test_choose_pdfs_custom_resolves_filename_against_source_dir(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    target = pdfs / "dietler2005-Introduction-EmbodiedMaterialCulture.pdf"
    target.write_bytes(b"%PDF-1.7\nfake")

    selected = pipeline.choose_pdfs(
        mode="custom",
        source_dir=str(pdfs),
        explicit_pdfs=["dietler2005-Introduction-EmbodiedMaterialCulture.pdf"],
        skip_existing=False,
        require_metadata=False,
    )

    assert selected == [target]


def test_choose_pdfs_custom_handles_brace_wrapped_placeholder_style(tmp_path: Path) -> None:
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    target = pdfs / "dietler1989-TichMatek-TechnologyOfLuoPotteryProductionDefinitionOfCeramicStyle.pdf"
    target.write_bytes(b"%PDF-1.7\nfake")

    selected = pipeline.choose_pdfs(
        mode="custom",
        source_dir=str(pdfs),
        explicit_pdfs=["{dietler1989-TichMatek-TechnologyOfLuoPotteryProductionDefinitionOfCeramicStyle.pdf}"],
        skip_existing=False,
        require_metadata=False,
    )

    assert selected == [target]


def test_ingest_pdfs_skips_bad_articles_and_returns_failures(monkeypatch, tmp_path: Path) -> None:
    p1 = tmp_path / "ok1.pdf"
    p2 = tmp_path / "bad.pdf"
    p3 = tmp_path / "ok2.pdf"
    for p in (p1, p2, p3):
        p.write_text("x")

    metadata_seen = {}

    def fake_load_article(pdf_path: Path, chunk_size_words: int, chunk_overlap_words: int, metadata=None):
        metadata_seen[pdf_path.name] = metadata
        if pdf_path == p2:
            raise ValueError("broken")
        return ArticleDoc(
            article_id=pdf_path.stem,
            title=pdf_path.stem,
            normalized_title=pdf_path.stem,
            year=2024,
            author="Author",
            authors=["Author"],
            citekey=None,
            paperpile_id=None,
            doi=None,
            journal=None,
            publisher=None,
            source_path=str(pdf_path),
            chunks=[
                Chunk(
                    chunk_id=f"{pdf_path.stem}::0",
                    index=0,
                    text="text",
                    tokens=["text"],
                    token_counts={"text": 1},
                    page_start=1,
                    page_end=1,
                )
            ],
            citations=[],
        )

    calls = {"setup": 0, "ingest_articles": 0, "close": 0}

    class FakeStore:
        embedding_dimension = 384

        def __init__(self, uri: str, user: str, password: str, embedding_model: str):
            self.args = (uri, user, password, embedding_model)

        def setup_schema(self, vector_dimensions: int):
            calls["setup"] += 1
            assert vector_dimensions == 384

        def ingest_articles(self, articles, should_cancel=None, article_progress_callback=None):
            calls["ingest_articles"] += 1
            assert len(articles) == 2

        def close(self):
            calls["close"] += 1

    monkeypatch.setattr(pipeline, "load_article", fake_load_article)
    monkeypatch.setattr(pipeline, "GraphStore", FakeStore)
    monkeypatch.setattr(
        pipeline,
        "load_paperpile_index",
        lambda _path: {
            "ok1.pdf": {"title": "From Paperpile", "authors": ["A One"]},
            "ok2.pdf": {"title": "From Paperpile 2", "authors": ["A Two"]},
            "bad.pdf": {"title": "Broken", "authors": ["Bad"]},
        },
    )

    summary = pipeline.ingest_pdfs(
        selected_pdfs=[p1, p2, p3],
        wipe=True,
        settings=Settings(),
        skip_existing=False,
    )

    assert summary.ingested_articles == 2
    assert summary.total_chunks == 2
    assert summary.total_references == 0
    assert summary.skipped_existing_pdfs == []
    assert len(summary.failed_pdfs) == 1
    assert summary.failed_pdfs[0]["pdf"] == str(p2)
    assert "broken" in summary.failed_pdfs[0]["error"]
    assert calls == {"setup": 1, "ingest_articles": 1, "close": 1}
    assert metadata_seen["ok1.pdf"]["title"] == "From Paperpile"
    assert metadata_seen["bad.pdf"]["title"] == "Broken"


def test_ingest_pdfs_raises_if_all_fail(monkeypatch, tmp_path: Path) -> None:
    p1 = tmp_path / "bad.pdf"
    p1.write_text("x")

    def always_fail(**kwargs):
        raise RuntimeError("nope")

    monkeypatch.setattr(pipeline, "load_article", always_fail)
    monkeypatch.setattr(pipeline, "load_paperpile_index", lambda _path: {"bad.pdf": {"title": "bad"}})

    with pytest.raises(ValueError, match="No readable PDFs were ingested"):
        pipeline.ingest_pdfs(selected_pdfs=[p1], settings=Settings(), skip_existing=False)


def test_ingest_pdfs_returns_zero_when_no_metadata_matches(monkeypatch, tmp_path: Path) -> None:
    p1 = tmp_path / "bad.pdf"
    p1.write_text("x")
    monkeypatch.setattr(pipeline, "load_paperpile_index", lambda _path: {})

    summary = pipeline.ingest_pdfs(selected_pdfs=[p1], settings=Settings(), skip_existing=False)
    assert summary.ingested_articles == 0
    assert summary.skipped_no_metadata_pdfs == [str(p1)]


def test_choose_pdfs_test3_skips_existing_and_returns_three_fresh(monkeypatch, tmp_path: Path) -> None:
    files = []
    for i in range(1, 6):
        p = tmp_path / f"f{i}.pdf"
        p.write_bytes(b"%PDF-1.7\nfake")
        files.append(p)

    monkeypatch.setattr(pipeline, "_get_existing_article_ids", lambda settings: {"f1", "f2"})
    selected = pipeline.choose_pdfs(
        mode="test3",
        source_dir=str(tmp_path),
        skip_existing=True,
        require_metadata=False,
        settings=Settings(),
    )

    assert selected == [files[2], files[3], files[4]]


def test_choose_pdfs_override_includes_existing(monkeypatch, tmp_path: Path) -> None:
    p1 = tmp_path / "a.pdf"
    p2 = tmp_path / "b.pdf"
    p1.write_bytes(b"%PDF-1.7\nfake")
    p2.write_bytes(b"%PDF-1.7\nfake")

    monkeypatch.setattr(pipeline, "_get_existing_article_ids", lambda settings: {"a", "b"})
    selected = pipeline.choose_pdfs(
        mode="test3",
        source_dir=str(tmp_path),
        skip_existing=False,
        require_metadata=False,
        settings=Settings(),
    )

    assert selected == [p1, p2]


def test_choose_pdfs_skips_files_without_metadata_by_default(monkeypatch, tmp_path: Path) -> None:
    p1 = tmp_path / "m1.pdf"
    p2 = tmp_path / "m2.pdf"
    p1.write_bytes(b"%PDF-1.7\nfake")
    p2.write_bytes(b"%PDF-1.7\nfake")

    monkeypatch.setattr(pipeline, "_get_existing_article_ids", lambda settings: set())
    monkeypatch.setattr(pipeline, "load_paperpile_index", lambda _path: {"m1.pdf": {"title": "Only One"}})

    selected = pipeline.choose_pdfs(mode="all", source_dir=str(tmp_path), skip_existing=False, settings=Settings())
    assert selected == [p1]
