from __future__ import annotations

import re
from typing import Any

from .neo4j_store import GraphStore
from .pdf_processing import STOPWORDS


def tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


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
    return ranked[:limit]

