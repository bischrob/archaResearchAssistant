from __future__ import annotations

import re
from typing import Any

from .neo4j_store import GraphStore
from .pdf_processing import STOPWORDS

INTENT_STOPWORDS = {
    "summarize",
    "summary",
    "simple",
    "simply",
    "explain",
    "explanation",
    "terms",
    "overview",
    "describe",
    "discuss",
    "research",
    "work",
    "paper",
    "papers",
}


def tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and t not in INTENT_STOPWORDS and len(t) > 1]


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9'-]*", (text or "").lower()))


def parse_query_terms(query: str) -> dict[str, Any]:
    tokens = tokenize_query(query)
    # Preserve token order while removing duplicates.
    dedup_tokens = list(dict.fromkeys(tokens))
    years = {int(y) for y in re.findall(r"\b(19\d{2}|20\d{2})\b", query)}
    phrases = [p.strip().lower() for p in re.findall(r'"([^"]+)"', query) if p.strip()]
    author_terms = [t for t in dedup_tokens if len(t) >= 4]
    # Likely proper-noun/acronym terms from original question are high-priority.
    raw_terms = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", query)
    must_terms = []
    for raw in raw_terms:
        if len(raw) < 4:
            continue
        if any(ch.isupper() for ch in raw[1:]) or raw.isupper():
            must_terms.append(raw.lower())
    must_terms = list(dict.fromkeys(must_terms))
    return {
        "tokens": dedup_tokens,
        "years": years,
        "phrases": phrases,
        "author_terms": author_terms,
        "must_terms": must_terms,
    }


def rerank_hits(query: str, hits: list[dict[str, Any]], top_k: int, plan: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    parsed = plan or parse_query_terms(query)
    q_tokens = set(parsed["tokens"])
    q_years = set(parsed["years"])
    q_phrases = parsed["phrases"]
    if not q_tokens:
        return hits[:top_k]
    for row in hits:
        chunk_text = row.get("chunk_text") or ""
        title_text = row.get("article_title") or ""
        authors_text = " ".join(row.get("authors") or ([row.get("author")] if row.get("author") else []))
        c_tokens = _token_set(chunk_text)
        t_tokens = _token_set(title_text)
        a_tokens = _token_set(authors_text)

        denom = max(1, len(q_tokens))
        chunk_overlap = len(q_tokens & c_tokens) / denom
        title_overlap = len(q_tokens & t_tokens) / denom
        author_overlap = len(q_tokens & a_tokens) / denom
        year_match = 1.0 if (q_years and row.get("article_year") in q_years) else 0.0
        phrase_match = 0.0
        if q_phrases:
            lowered_chunk = chunk_text.lower()
            lowered_title = title_text.lower()
            phrase_hits = sum(1 for p in q_phrases if p in lowered_chunk or p in lowered_title)
            phrase_match = phrase_hits / max(1, len(q_phrases))
        graph_bonus = min(0.2, 0.03 * (len(row.get("cites_out") or []) + len(row.get("cited_by") or [])))

        base = float(row.get("combined_score", 0.0))
        token_component = float(row.get("token_score", 0.0)) / 12.0
        vector_component = float(row.get("vector_score", 0.0))
        author_component = 0.2 * float(row.get("author_score", 0.0))
        semantic = max(base, vector_component + token_component + author_component)
        row["rerank_score"] = (
            semantic
            + (0.45 * chunk_overlap)
            + (0.40 * title_overlap)
            + (0.70 * author_overlap)
            + (0.30 * year_match)
            + (0.30 * phrase_match)
            + graph_bonus
        )
        row["query_features"] = {
            "chunk_overlap": round(chunk_overlap, 4),
            "title_overlap": round(title_overlap, 4),
            "author_overlap": round(author_overlap, 4),
            "year_match": year_match,
            "phrase_match": round(phrase_match, 4),
        }
    return sorted(hits, key=lambda x: x.get("rerank_score", 0.0), reverse=True)[:top_k]


def contextual_retrieve(store: GraphStore, query: str, limit: int = 8) -> list[dict[str, Any]]:
    plan = parse_query_terms(query)
    candidate_k = max(limit * 5, 25)
    vector_hits = store.vector_query(query, limit=candidate_k)
    token_hits = store.token_query(plan["tokens"], limit=candidate_k)
    author_hits = store.author_query(plan["author_terms"], limit=candidate_k)
    title_hits = store.title_query(plan["tokens"], limit=candidate_k)

    by_chunk: dict[str, dict[str, Any]] = {}
    for row in vector_hits:
        row["combined_score"] = float(row.get("vector_score", 0.0))
        row["retrieval_sources"] = ["vector"]
        by_chunk[row["chunk_id"]] = row

    for row in token_hits:
        cid = row["chunk_id"]
        token_score = float(row.get("token_score", 0.0))
        if cid in by_chunk:
            by_chunk[cid]["combined_score"] += token_score / 10.0
            by_chunk[cid].setdefault("retrieval_sources", []).append("token")
            by_chunk[cid]["token_score"] = token_score
        else:
            row["combined_score"] = token_score / 10.0
            row["retrieval_sources"] = ["token"]
            by_chunk[cid] = row

    for row in author_hits:
        cid = row["chunk_id"]
        author_score = float(row.get("author_score", 0.0))
        if cid in by_chunk:
            by_chunk[cid]["combined_score"] += min(1.5, 0.3 * author_score)
            by_chunk[cid].setdefault("retrieval_sources", []).append("author")
            by_chunk[cid]["author_score"] = author_score
        else:
            row["combined_score"] = min(1.5, 0.3 * author_score)
            row["retrieval_sources"] = ["author"]
            by_chunk[cid] = row

    for row in title_hits:
        cid = row["chunk_id"]
        title_score = float(row.get("title_score", 0.0))
        if cid in by_chunk:
            by_chunk[cid]["combined_score"] += min(2.0, 0.35 * title_score)
            by_chunk[cid].setdefault("retrieval_sources", []).append("title")
            by_chunk[cid]["title_score"] = title_score
        else:
            row["combined_score"] = min(2.0, 0.35 * title_score)
            row["retrieval_sources"] = ["title"]
            by_chunk[cid] = row

    ranked = sorted(by_chunk.values(), key=lambda x: x.get("combined_score", 0.0), reverse=True)

    must_terms = plan.get("must_terms") or []
    if must_terms:
        strict = []
        for row in ranked:
            hay = " ".join(
                [
                    str(row.get("article_title") or ""),
                    str(row.get("chunk_text") or ""),
                    " ".join(row.get("authors") or ([row.get("author")] if row.get("author") else [])),
                    str(row.get("article_citekey") or ""),
                ]
            ).lower()
            if any(mt in hay for mt in must_terms):
                strict.append(row)
        if strict:
            ranked = strict

    primary = rerank_hits(query, ranked, top_k=limit, plan=plan)

    # Low-confidence fallback: if no top row meaningfully matches title/author fields,
    # force-add author channel candidates and rerank.
    max_signal = max(
        (
            float((r.get("query_features") or {}).get("author_overlap", 0.0))
            + float((r.get("query_features") or {}).get("title_overlap", 0.0))
            for r in primary
        ),
        default=0.0,
    )
    if max_signal < 0.15 and author_hits:
        merged = dict(by_chunk)
        for row in author_hits[: max(limit * 2, 10)]:
            merged[row["chunk_id"]] = merged.get(row["chunk_id"], row)
        primary = rerank_hits(query, list(merged.values()), top_k=limit, plan=plan)

    return primary
