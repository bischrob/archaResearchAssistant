from __future__ import annotations

import builtins

import pytest

from src.rag.search_graphrag import graphrag_retrieve


class _FakeStore:
    def vector_query(self, query: str, limit: int):
        return []

    def title_query(self, terms, limit: int):
        return []

    def token_query(self, terms, limit: int):
        return []


def test_graphrag_retrieve_requires_dependency(monkeypatch) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("neo4j_graphrag"):
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match="neo4j-graphrag is required"):
        graphrag_retrieve(_FakeStore(), "query")
