from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .neo4j_store import GraphStore


def _require_graphrag() -> None:
    try:
        import neo4j_graphrag  # type: ignore # noqa: F401
        from neo4j_graphrag import retrievers as _retrievers  # type: ignore # noqa: F401
    except Exception as exc:
        raise RuntimeError(
            "neo4j-graphrag is required for search. Install and configure neo4j-graphrag; legacy retrieval is disabled."
        ) from exc
    required = ("VectorRetriever", "FulltextRetriever", "HybridRetriever")
    missing = [name for name in required if not hasattr(_retrievers, name)]
    if missing:
        raise RuntimeError(
            f"neo4j-graphrag retriever classes are unavailable: {', '.join(missing)}. Legacy retrieval is disabled."
        )


def graphrag_retrieve(
    store: "GraphStore",
    query: str,
    *,
    limit: int = 20,
    limit_scope: str = "papers",
    chunks_per_paper: int = 8,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    _require_graphrag()
    vector_rows = store.vector_query(query, limit=max(limit, 1))
    fulltext_rows = store.title_query(query.split(), limit=max(limit, 1))
    hybrid_rows = store.token_query(query.split(), limit=max(limit, 1))

    by_chunk: dict[str, dict[str, Any]] = {}
    for source_name, rows in (("vector", vector_rows), ("fulltext", fulltext_rows), ("hybrid", hybrid_rows)):
        for row in rows:
            cid = str(row.get("chunk_id") or "")
            if not cid:
                continue
            score = float(row.get("vector_score") or row.get("title_score") or row.get("token_score") or 0.0)
            base = by_chunk.setdefault(cid, dict(row))
            base.setdefault("retrieval_sources", [])
            if source_name not in base["retrieval_sources"]:
                base["retrieval_sources"].append(source_name)
            base["combined_score"] = max(float(base.get("combined_score", 0.0)), score)
            base["graph_context"] = {
                "citation_neighbors": row.get("cites_out") or [],
                "cited_by_neighbors": row.get("cited_by") or [],
                "author_neighbors": row.get("authors") or [],
                "section_neighbors": [row.get("section_label")] if row.get("section_label") else [],
            }

    rows = sorted(by_chunk.values(), key=lambda r: float(r.get("combined_score", 0.0)), reverse=True)
    if score_threshold is not None:
        rows = [r for r in rows if float(r.get("combined_score", 0.0)) >= float(score_threshold)]

    scope = (limit_scope or "papers").strip().lower()
    if scope != "papers":
        return rows[:limit]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        article_id = str(row.get("article_id") or row.get("article_title") or "").strip()
        if not article_id:
            continue
        grouped.setdefault(article_id, []).append(row)
    papers: list[dict[str, Any]] = []
    for article_rows in grouped.values():
        ranked = sorted(article_rows, key=lambda r: float(r.get("combined_score", 0.0)), reverse=True)
        top = dict(ranked[0])
        top["result_scope"] = "paper"
        top["highlight_chunks"] = ranked[: max(1, int(chunks_per_paper))]
        papers.append(top)
    papers.sort(key=lambda r: float(r.get("combined_score", 0.0)), reverse=True)
    return papers[:limit]
