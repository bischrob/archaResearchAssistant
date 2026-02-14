from __future__ import annotations

import re
from typing import Any

from .neo4j_store import GraphStore
from .pdf_processing import STOPWORDS


def tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def rerank_hits(query: str, hits: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    q_tokens = set(tokenize_query(query))
    if not q_tokens:
        return hits[:top_k]
    for row in hits:
        text = (row.get("chunk_text") or "").lower()
        c_tokens = set(re.findall(r"[a-z][a-z0-9'-]*", text))
        overlap = len(q_tokens & c_tokens)
        denom = max(1, len(q_tokens))
        lexical = overlap / denom
        row["rerank_score"] = float(row.get("combined_score", 0.0)) + (0.5 * lexical)
    return sorted(hits, key=lambda x: x.get("rerank_score", 0.0), reverse=True)[:top_k]


def contextual_retrieve(store: GraphStore, query: str, limit: int = 8) -> list[dict[str, Any]]:
    vector_hits = store.vector_query(query, limit=limit)
    token_hits = store.token_query(tokenize_query(query), limit=limit)

    by_chunk: dict[str, dict[str, Any]] = {}
    for row in vector_hits:
        row["combined_score"] = float(row.get("vector_score", 0.0))
        by_chunk[row["chunk_id"]] = row

    for row in token_hits:
        cid = row["chunk_id"]
        token_score = float(row.get("token_score", 0.0))
        if cid in by_chunk:
            by_chunk[cid]["combined_score"] += token_score / 10.0
        else:
            row["combined_score"] = token_score / 10.0
            by_chunk[cid] = row

    ranked = sorted(by_chunk.values(), key=lambda x: x["combined_score"], reverse=True)
    return rerank_hits(query, ranked, top_k=limit)
