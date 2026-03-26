from __future__ import annotations

import logging
import os
import re
import threading
from typing import Any

from .neo4j_store import GraphStore
from .pdf_processing import STOPWORDS

LOGGER = logging.getLogger(__name__)
_VECTOR_QUERY_TIMEOUT_SECONDS = max(0.0, float(os.getenv("RA_VECTOR_QUERY_TIMEOUT_SECONDS", "20")))

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

REFERENCE_SECTION_HINTS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
}

FACET_STOPWORDS = {
    "already",
    "directly",
    "establish",
    "establishes",
    "evidence",
    "mature",
    "paper",
    "papers",
    "research",
    "review",
    "shows",
    "source",
    "study",
    "substantial",
}


ARCHAEOLOGY_DOMAIN_TERMS = {
    "hohokam",
    "anasazi",
    "mogollon",
    "fremont",
    "arizona",
    "utah",
    "sonoran",
    "southwestern",
    "projectile",
    "point",
    "points",
    "arrowhead",
    "arrowheads",
    "dart",
    "darts",
    "lithic",
    "typology",
    "typological",
    "ceramic",
    "pottery",
}

ARCHAEOLOGY_ANCHOR_TERMS = {
    "hohokam",
    "anasazi",
    "mogollon",
    "fremont",
    "arizona",
    "utah",
    "sonoran",
    "southwestern",
}


def tokenize_query(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower())
    return [t for t in tokens if t not in STOPWORDS and t not in INTENT_STOPWORDS and len(t) > 1]


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9'-]*", (text or "").lower()))


def _looks_like_reference_chunk(text: str) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if any(lowered.startswith(hint) for hint in REFERENCE_SECTION_HINTS):
        return True
    lines = [ln.strip() for ln in lowered.splitlines() if ln.strip()]
    if not lines:
        return False
    doi_count = lowered.count("doi")
    year_hits = re.findall(r"\b(?:19|20)\d{2}\b", lowered)
    return doi_count >= 2 or len(year_hits) >= 5


def _critical_claim_tokens(text: str) -> list[str]:
    tokens = tokenize_query(text)
    out = []
    for token in tokens:
        if token in FACET_STOPWORDS:
            continue
        if len(token) < 4:
            continue
        out.append(token)
    return list(dict.fromkeys(out))


def _archaeology_required(text: str) -> bool:
    lowered = (text or "").lower()
    return "archaeolog" in lowered


def _domain_penalty(claim_text: str, article_title: str, chunk_text: str) -> float:
    if not _archaeology_required(claim_text):
        return 0.0
    hay = f"{article_title} {chunk_text}".lower()
    if "archaeolog" in hay:
        return 0.0
    return 0.28


def _contradiction_penalty(claim_text: str, article_title: str, chunk_text: str) -> float:
    claim = (claim_text or "").lower()
    hay = f"{article_title} {chunk_text}".lower()
    penalty = 0.0
    if "without" in claim and "review" in claim:
        contradictory = [
            "human review",
            "expert review",
            "expert human review",
            "requires human review",
            "remain complementary to expert human review",
            "complementary to expert human review",
        ]
        if any(phrase in hay for phrase in contradictory):
            penalty += 0.35
    if any(term in claim for term in ("directly establishes", "direct support", "solved")):
        hedges = [
            "limitations",
            "limited",
            "cautious",
            "future directions",
            "requires",
            "remain complementary",
        ]
        if any(term in hay for term in hedges):
            penalty += 0.12
    return penalty


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
        lowered = raw.lower()
        if any(ch.isupper() for ch in raw[1:]) or raw.isupper() or lowered in ARCHAEOLOGY_DOMAIN_TERMS:
            must_terms.append(lowered)
    must_terms = list(dict.fromkeys(must_terms))
    domain_terms = [token for token in dedup_tokens if token in ARCHAEOLOGY_DOMAIN_TERMS]
    anchor_terms = [token for token in dedup_tokens if token in ARCHAEOLOGY_ANCHOR_TERMS]
    return {
        "tokens": dedup_tokens,
        "years": years,
        "phrases": phrases,
        "author_terms": author_terms,
        "must_terms": must_terms,
        "domain_terms": domain_terms,
        "anchor_terms": anchor_terms,
    }


def article_claim_match(
    store: GraphStore,
    citekey: str,
    claim_text: str,
    top_k: int = 3,
) -> dict[str, Any]:
    article = store.article_chunks_by_citekey(citekey)
    if not article:
        return {
            "ok": False,
            "citekey": citekey,
            "claim_text": claim_text,
            "error": f"Article not found for citekey: {citekey}",
        }
    return score_article_claim(article, claim_text, top_k=top_k)


def article_claim_match_by_article_id(
    store: GraphStore,
    article_id: str,
    claim_text: str,
    top_k: int = 3,
) -> dict[str, Any]:
    article = store.article_chunks_by_id(article_id)
    if not article:
        return {
            "ok": False,
            "article_id": article_id,
            "claim_text": claim_text,
            "error": f"Article not found for id: {article_id}",
        }
    return score_article_claim(article, claim_text, top_k=top_k)


def score_article_claim(
    article: dict[str, Any],
    claim_text: str,
    top_k: int = 3,
) -> dict[str, Any]:
    plan = parse_query_terms(claim_text)
    q_tokens = set(plan["tokens"])
    q_years = set(plan["years"])
    q_phrases = plan["phrases"]
    article_year = article.get("article_year")
    scored_chunks: list[dict[str, Any]] = []

    for chunk in article.get("chunks") or []:
        chunk_text = str(chunk.get("text") or "")
        title_text = str(article.get("article_title") or "")
        c_tokens = _token_set(chunk_text)
        title_tokens = _token_set(title_text)
        denom = max(1, len(q_tokens))
        token_overlap = len(q_tokens & c_tokens) / denom if q_tokens else 0.0
        title_overlap = len(q_tokens & title_tokens) / denom if q_tokens else 0.0
        phrase_match = 0.0
        if q_phrases:
            lowered_chunk = chunk_text.lower()
            lowered_title = title_text.lower()
            phrase_hits = sum(1 for phrase in q_phrases if phrase in lowered_chunk or phrase in lowered_title)
            phrase_match = phrase_hits / max(1, len(q_phrases))
        year_match = 1.0 if (q_years and article_year in q_years) else 0.0
        density_bonus = min(0.25, 0.04 * len(q_tokens & c_tokens))
        reference_penalty = 0.45 if _looks_like_reference_chunk(chunk_text) else 0.0
        critical_tokens = _critical_claim_tokens(claim_text)
        critical_denom = max(1, len(critical_tokens))
        critical_overlap = len(set(critical_tokens) & (c_tokens | title_tokens)) / critical_denom if critical_tokens else 0.0
        domain_penalty = _domain_penalty(claim_text, title_text, chunk_text)
        contradiction_penalty = _contradiction_penalty(claim_text, title_text, chunk_text)
        support_score = (
            (0.9 * token_overlap)
            + (0.2 * title_overlap)
            + (0.55 * phrase_match)
            + (0.2 * year_match)
            + density_bonus
            + (0.35 * critical_overlap)
            - reference_penalty
            - domain_penalty
            - contradiction_penalty
        )
        scored_chunks.append(
            {
                "chunk_id": chunk.get("id"),
                "chunk_index": chunk.get("index"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "chunk_text": chunk_text,
                "support_score": round(support_score, 6),
                "support_features": {
                    "token_overlap": round(token_overlap, 4),
                    "title_overlap": round(title_overlap, 4),
                    "phrase_match": round(phrase_match, 4),
                    "year_match": year_match,
                    "critical_overlap": round(critical_overlap, 4),
                    "domain_penalty": domain_penalty,
                    "contradiction_penalty": contradiction_penalty,
                    "reference_penalty": reference_penalty,
                },
            }
        )

    scored_chunks.sort(key=lambda row: row.get("support_score", 0.0), reverse=True)
    top_chunks = scored_chunks[: max(1, int(top_k))]
    top_score = float(top_chunks[0].get("support_score", 0.0)) if top_chunks else 0.0
    top_features = (top_chunks[0].get("support_features") or {}) if top_chunks else {}
    critical_overlap = float(top_features.get("critical_overlap", 0.0))
    contradiction_penalty = float(top_features.get("contradiction_penalty", 0.0))

    if top_score >= 0.95 and critical_overlap >= 0.45 and contradiction_penalty == 0.0:
        classification = "direct_support"
    elif top_score >= 0.45:
        classification = "adjacent_or_partial_support"
    else:
        classification = "not_supported"

    return {
        "ok": True,
        "citekey": article.get("article_citekey"),
        "article_id": article.get("article_id"),
        "claim_text": claim_text,
        "classification": classification,
        "top_support_score": round(top_score, 6),
        "article": {
            "article_id": article.get("article_id"),
            "article_title": article.get("article_title"),
            "article_year": article.get("article_year"),
            "article_citekey": article.get("article_citekey"),
            "article_doi": article.get("article_doi"),
            "article_source_path": article.get("article_source_path"),
            "authors": article.get("authors") or [],
        },
        "supporting_chunks": top_chunks,
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
        domain_terms = set(parsed.get("domain_terms") or [])
        anchor_terms = set(parsed.get("anchor_terms") or [])
        hay = f"{title_text} {chunk_text}".lower()
        domain_hits = sum(1 for term in domain_terms if term in hay)
        anchor_hits = sum(1 for term in anchor_terms if term in hay)
        if domain_terms:
            row["rerank_score"] += min(0.75, 0.18 * domain_hits)
            if domain_hits == 0:
                row["rerank_score"] -= 0.45
        if anchor_terms:
            row["rerank_score"] += min(0.9, 0.28 * anchor_hits)
            if anchor_hits == 0:
                row["rerank_score"] -= 1.1
        row["query_features"] = {
            "chunk_overlap": round(chunk_overlap, 4),
            "title_overlap": round(title_overlap, 4),
            "author_overlap": round(author_overlap, 4),
            "year_match": year_match,
            "phrase_match": round(phrase_match, 4),
            "domain_hits": domain_hits,
            "anchor_hits": anchor_hits,
        }
    return sorted(hits, key=lambda x: x.get("rerank_score", 0.0), reverse=True)[:top_k]


def _row_score(row: dict[str, Any]) -> float:
    return float(row.get("rerank_score", row.get("combined_score", 0.0)))


def _apply_score_threshold(rows: list[dict[str, Any]], score_threshold: float | None, *, fallback_limit: int) -> list[dict[str, Any]]:
    if score_threshold is None:
        return rows
    kept = [row for row in rows if _row_score(row) >= float(score_threshold)]
    if kept:
        return kept
    return rows[: max(1, int(fallback_limit))]


def _article_key(row: dict[str, Any]) -> str:
    for field in ("article_id", "article_citekey", "article_doi", "article_source_path", "article_title"):
        value = str(row.get(field) or "").strip()
        if value:
            return f"{field}:{value.lower()}"
    return f"chunk:{str(row.get('chunk_id') or '').strip().lower()}"


def _paper_results(rows: list[dict[str, Any]], limit: int, chunks_per_paper: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(_article_key(row), []).append(row)

    papers: list[dict[str, Any]] = []
    for group_rows in grouped.values():
        ranked_chunks = sorted(group_rows, key=_row_score, reverse=True)
        top = ranked_chunks[0]
        top_scores = [_row_score(r) for r in ranked_chunks[:2]]
        mean_top = sum(top_scores) / max(1, len(top_scores))
        source_diversity = len({src for r in ranked_chunks for src in (r.get("retrieval_sources") or [])})
        paper_score = _row_score(top) + (0.2 * mean_top) + (0.06 * source_diversity)

        highlights = []
        for row in ranked_chunks[:chunks_per_paper]:
            highlights.append(
                {
                    "chunk_id": row.get("chunk_id"),
                    "chunk_index": row.get("chunk_index"),
                    "page_start": row.get("page_start"),
                    "page_end": row.get("page_end"),
                    "chunk_text": row.get("chunk_text"),
                    "score": round(_row_score(row), 6),
                    "retrieval_sources": row.get("retrieval_sources") or [],
                }
            )

        paper = dict(top)
        paper["result_scope"] = "paper"
        paper["paper_score"] = round(paper_score, 6)
        paper["paper_chunk_count"] = len(ranked_chunks)
        paper["paper_retrieval_sources"] = sorted(
            {src for row in ranked_chunks for src in (row.get("retrieval_sources") or [])}
        )
        paper["highlight_chunks"] = highlights
        # Keep compatibility with existing UI that reads `combined_score`.
        paper["combined_score"] = paper["paper_score"]
        paper["rerank_score"] = paper["paper_score"]
        papers.append(paper)

    papers.sort(key=lambda row: row.get("paper_score", 0.0), reverse=True)
    return papers[:limit]


def _safe_vector_query(store: GraphStore, query: str, limit: int) -> list[dict[str, Any]]:
    if _VECTOR_QUERY_TIMEOUT_SECONDS <= 0:
        return store.vector_query(query, limit=limit)

    result_box: dict[str, Any] = {}
    error_box: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result_box["rows"] = store.vector_query(query, limit=limit)
        except BaseException as exc:  # pragma: no cover - surfaced below
            error_box["error"] = exc

    worker = threading.Thread(target=_runner, daemon=True)
    worker.start()
    worker.join(_VECTOR_QUERY_TIMEOUT_SECONDS)
    if worker.is_alive():
        LOGGER.warning(
            "Vector query timed out after %.1fs for %r; falling back to lexical retrieval channels.",
            _VECTOR_QUERY_TIMEOUT_SECONDS,
            query,
        )
        return []
    if "error" in error_box:
        raise error_box["error"]
    return list(result_box.get("rows") or [])


def contextual_retrieve(
    store: GraphStore,
    query: str,
    limit: int = 8,
    limit_scope: str = "chunks",
    chunks_per_paper: int = 1,
    score_threshold: float | None = None,
) -> list[dict[str, Any]]:
    scope = (limit_scope or "chunks").strip().lower()
    if scope not in {"chunks", "papers"}:
        scope = "chunks"
    chunks_per_paper = max(1, int(chunks_per_paper))

    plan = parse_query_terms(query)
    candidate_k = max(limit * (8 if scope == "papers" else 5), 80 if scope == "papers" else 25)
    rerank_limit = max(limit * 8, 80) if scope == "papers" else limit

    vector_hits = _safe_vector_query(store, query, limit=candidate_k)
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
    domain_terms = plan.get("domain_terms") or []
    anchor_terms = plan.get("anchor_terms") or []
    strict_mode = len(set(domain_terms)) >= 2 or len(set(must_terms)) >= 2 or len(set(anchor_terms)) >= 2
    if strict_mode:
        strict = []
        required_hits = 1 if not domain_terms else min(2, len(set(domain_terms)))
        for row in ranked:
            hay = " ".join(
                [
                    str(row.get("article_title") or ""),
                    str(row.get("chunk_text") or ""),
                    " ".join(row.get("authors") or ([row.get("author")] if row.get("author") else [])),
                    str(row.get("article_citekey") or ""),
                ]
            ).lower()
            non_generic_must_terms = [mt for mt in must_terms if mt not in {"projectile", "point", "points", "ceramic", "pottery", "lithic", "typology", "typological"}]
            must_hit = any(mt in hay for mt in non_generic_must_terms) if non_generic_must_terms else True
            domain_hit_count = sum(1 for term in domain_terms if term in hay)
            anchor_hit_count = sum(1 for term in anchor_terms if term in hay)
            anchor_ok = True if len(set(anchor_terms)) < 2 else anchor_hit_count >= 1
            if must_hit and anchor_ok and domain_hit_count >= required_hits:
                strict.append(row)
        if strict:
            ranked = strict

    primary = rerank_hits(query, ranked, top_k=min(rerank_limit, len(ranked)), plan=plan)

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
        for row in author_hits[: max(limit * (4 if scope == "papers" else 2), 10)]:
            merged[row["chunk_id"]] = merged.get(row["chunk_id"], row)
        primary = rerank_hits(
            query,
            list(merged.values()),
            top_k=min(rerank_limit, len(merged)),
            plan=plan,
        )

    if scope == "papers":
        papers = _paper_results(primary, limit=max(limit, len(primary)), chunks_per_paper=chunks_per_paper)
        papers = _apply_score_threshold(papers, score_threshold, fallback_limit=limit)
        return papers[:limit] if score_threshold is None else papers
    rows = _apply_score_threshold(primary, score_threshold, fallback_limit=limit)
    return rows[:limit] if score_threshold is None else rows
