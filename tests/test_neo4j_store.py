from __future__ import annotations

from dataclasses import dataclass, field
import json

import numpy as np
import pytest

import src.rag.neo4j_store as neo4j_store
from src.rag.neo4j_store import GraphStore, SentenceTransformerEmbedder
from src.rag.pdf_processing import ArticleDoc, Chunk


class _FakeSentenceTransformer:
    def __init__(self, model_name, device=None):
        self.model_name = model_name
        self.device = device
        self.calls = []

    def get_sentence_embedding_dimension(self):
        return 3

    def encode(self, texts, batch_size=0, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True):
        self.calls.append(
            {
                "texts": list(texts),
                "batch_size": batch_size,
                "show_progress_bar": show_progress_bar,
                "convert_to_numpy": convert_to_numpy,
                "normalize_embeddings": normalize_embeddings,
            }
        )
        return np.array([[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32)


@dataclass
class _FakeTx:
    queries: list[str] = field(default_factory=list)
    kwargs_rows: list[dict] = field(default_factory=list)

    def run(self, query: str, **kwargs):
        self.queries.append(query)
        self.kwargs_rows.append(kwargs)
        return []


class _FakeSession:
    def __init__(self):
        self.execute_calls = 0
        self.tx_queries: list[str] = []
        self.tx_kwargs: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _tb):
        return False

    def execute_write(self, fn, *args):
        self.execute_calls += 1
        tx = _FakeTx()
        out = fn(tx, *args)
        self.tx_queries.extend(tx.queries)
        self.tx_kwargs.extend(tx.kwargs_rows)
        return out

    def run(self, _query: str, **_kwargs):
        return []


class _FakeDriver:
    def __init__(self):
        self.sessions: list[_FakeSession] = []

    def session(self):
        s = _FakeSession()
        self.sessions.append(s)
        return s

    def close(self):
        return None


def _mk_article(
    article_id: str,
    author,
    authors: list[str],
    year: int | None,
    chunks: list[Chunk],
) -> ArticleDoc:
    return ArticleDoc(
        article_id=article_id,
        title=f"Title {article_id}",
        normalized_title=f"title {article_id}",
        year=year,
        author=author,
        authors=authors,
        citekey=None,
        paperpile_id=None,
        doi=None,
        journal=None,
        publisher=None,
        source_path=f"/tmp/{article_id}.pdf",
        chunks=chunks,
        citations=[],
    )


def test_ingest_articles_zero_chunks_still_writes_article(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)
    store = GraphStore("bolt://unused", "neo4j", "pass")
    try:
        article = _mk_article(
            article_id="a1",
            author="Alice",
            authors=["Alice"],
            year=2024,
            chunks=[],
        )
        store.ingest_articles([article])
    finally:
        store.close()

    assert len(fake_driver.sessions) >= 1
    session = fake_driver.sessions[0]
    assert session.execute_calls == 1
    assert any("MERGE (a:Article {id: $id})" in q for q in session.tx_queries)
    assert any("OPTIONAL MATCH (:Author)-[w:WROTE]->(a)" in q for q in session.tx_queries)


def test_link_article_citations_handles_missing_authors(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)
    store = GraphStore("bolt://unused", "neo4j", "pass")
    try:
        source = _mk_article(
            article_id="src",
            author=None,
            authors=[],
            year=2025,
            chunks=[
                Chunk(
                    chunk_id="c1",
                    index=0,
                    text="A neutral paragraph with 2025 context.",
                    tokens=["neutral"],
                    token_counts={"neutral": 1},
                    page_start=1,
                    page_end=1,
                )
            ],
        )
        target = _mk_article(
            article_id="dst",
            author=None,
            authors=[],
            year=2024,
            chunks=[],
        )
        store._link_article_citations([source, target])
    finally:
        store.close()


def test_graph_store_uses_sentence_transformers_when_requested(monkeypatch):
    fake_driver = _FakeDriver()
    neo4j_store._EMBEDDER_CACHE.clear()

    class _FakeSentenceTransformer:
        def __init__(self, model_name, device=None):
            self.model_name = model_name
            self.device = device
            self.calls = []

        def get_sentence_embedding_dimension(self):
            return 3

        def encode(self, texts, batch_size=0, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True):
            self.calls.append(
                {
                    "texts": list(texts),
                    "batch_size": batch_size,
                    "show_progress_bar": show_progress_bar,
                    "convert_to_numpy": convert_to_numpy,
                    "normalize_embeddings": normalize_embeddings,
                }
            )
            return np.array([[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32)

    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "2")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")

    store = GraphStore("bolt://unused", "neo4j", "pass", embedding_model="sentence-transformers/all-MiniLM-L6-v2")
    try:
        assert isinstance(store.embedder, SentenceTransformerEmbedder)
        assert store.embedding_dimension == 3
        vectors = store.embedder.encode(["alpha", "beta"])
        assert len(vectors) == 2
        assert len(vectors[0]) == 3
        assert store.embedder.model.calls[0]["batch_size"] == 2
    finally:
        store.close()


@pytest.mark.parametrize(
    "provider,model_name,expected_message",
    [
        ("hash", "sentence-transformers/all-MiniLM-L6-v2", "hash placeholders are disabled"),
        ("auto", "hash", "Hash-based placeholder embeddings are no longer supported"),
    ],
)
def test_graph_store_rejects_hash_embedder_configuration(monkeypatch, provider, model_name, expected_message):
    fake_driver = _FakeDriver()
    neo4j_store._EMBEDDER_CACHE.clear()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setenv("EMBEDDING_PROVIDER", provider)
    with pytest.raises(ValueError, match=expected_message):
        GraphStore("bolt://unused", "neo4j", "pass", embedding_model=model_name)


def test_ingest_article_tx_persists_ocr_provenance(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)
    store = GraphStore("bolt://unused", "neo4j", "pass")
    try:
        article = ArticleDoc(
            article_id="ocr1",
            title="OCR Title",
            normalized_title="ocr title",
            year=2024,
            author="Alice",
            authors=["Alice"],
            citekey=None,
            paperpile_id=None,
            doi=None,
            journal=None,
            publisher=None,
            source_path="/tmp/ocr1.pdf",
            text_acquisition_method="native_pdf_plus_paddleocr_fallback",
            text_acquisition_fallback_used=True,
            text_quality_check_backend="heuristic_placeholder",
            native_text_malformed=True,
            native_text_malformed_reason="native_text_too_short",
            native_text_char_count=17,
            paddleocr_text_path="/tmp/ocr1.txt",
            ocr_engine="paddleocr",
            ocr_model="PaddleOCR[classic]:lang=en,device=cpu",
            ocr_version="3.0.0",
            ocr_processed_at="2026-03-21T22:00:00Z",
            ocr_quality_summary="heuristic:existing_sidecar;lines=2;pages=1;chars=40;tokens=6;alpha_ratio=0.850;suspect_ratio=0.000;native_reason=native_text_too_short",
            chunks=[],
            citations=[],
        )
        store.ingest_articles([article])
    finally:
        store.close()

    session = fake_driver.sessions[0]
    article_write = next(kwargs for query, kwargs in zip(session.tx_queries, session.tx_kwargs) if "MERGE (a:Article {id: $id})" in query)
    assert article_write["ocr_engine"] == "paddleocr"
    assert article_write["ocr_model"] == "PaddleOCR[classic]:lang=en,device=cpu"
    assert article_write["ocr_version"] == "3.0.0"
    assert article_write["ocr_processed_at"] == "2026-03-21T22:00:00Z"
    assert "native_reason=native_text_too_short" in article_write["ocr_quality_summary"]


def test_ingest_article_tx_serializes_keyword_audit_to_json(monkeypatch):
    fake_driver = _FakeDriver()
    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", _FakeSentenceTransformer)
    store = GraphStore("bolt://unused", "neo4j", "pass")
    try:
        article = ArticleDoc(
            article_id="kw1",
            title="Keyword Audit Title",
            normalized_title="keyword audit title",
            year=2024,
            author="Alice",
            authors=["Alice"],
            citekey=None,
            paperpile_id=None,
            doi=None,
            journal=None,
            publisher=None,
            source_path="/tmp/kw1.pdf",
            chunks=[],
            citations=[],
            keyword_extraction_method="heuristic",
            keyword_extraction_audit={
                "method": "heuristic",
                "keyword_count": 2,
                "source_sections": ["body"],
                "sample": [
                    {"value": "platform", "score": 0.9},
                    {"value": "mounds", "score": 0.8},
                ],
            },
        )
        store.ingest_articles([article])
    finally:
        store.close()

    session = fake_driver.sessions[0]
    article_write = next(kwargs for query, kwargs in zip(session.tx_queries, session.tx_kwargs) if "MERGE (a:Article {id: $id})" in query)
    assert article_write["keyword_extraction_audit_json"] is not None
    decoded = json.loads(article_write["keyword_extraction_audit_json"])
    assert decoded["method"] == "heuristic"
    assert decoded["keyword_count"] == 2
    assert decoded["sample"][0]["value"] == "platform"


def test_graph_store_reuses_cached_embedder_for_same_configuration(monkeypatch):
    fake_driver = _FakeDriver()
    neo4j_store._EMBEDDER_CACHE.clear()

    created: list[_FakeSentenceTransformer] = []

    class TrackingSentenceTransformer(_FakeSentenceTransformer):
        def __init__(self, model_name, device=None):
            super().__init__(model_name, device=device)
            created.append(self)

    monkeypatch.setattr("src.rag.neo4j_store.GraphDatabase.driver", lambda *_args, **_kwargs: fake_driver)
    monkeypatch.setattr("src.rag.neo4j_store.SentenceTransformer", TrackingSentenceTransformer)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "8")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    try:
        store_a = GraphStore("bolt://unused", "neo4j", "pass", embedding_model="sentence-transformers/all-MiniLM-L6-v2")
        store_b = GraphStore("bolt://unused", "neo4j", "pass", embedding_model="sentence-transformers/all-MiniLM-L6-v2")
        assert store_a.embedder is store_b.embedder
        assert len(created) == 1
    finally:
        store_a.close()
        store_b.close()
