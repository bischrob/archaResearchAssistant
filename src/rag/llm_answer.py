from __future__ import annotations

import re
from typing import Any

from .config import Settings


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "did",
    "do",
    "does",
    "for",
    "from",
    "how",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "say",
    "says",
    "that",
    "the",
    "their",
    "them",
    "these",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "with",
}

REWRITE_GENERIC_TOKENS = {
    "archaeology",
    "archaeological",
    "article",
    "evidence",
    "paper",
    "papers",
    "research",
    "study",
    "studies",
    "summary",
    "overview",
    "method",
    "methods",
}

DOMAIN_PLACE_TERMS = {"arizona", "utah", "mexico", "southwestern", "sonoran", "four", "corners"}
ARTIFACT_FAMILY_TERMS = {
    "projectile": {"projectile", "point", "points", "arrowhead", "arrowheads", "dart", "darts", "lithic", "biface", "bifaces", "typology", "typological"},
    "ceramic": {"ceramic", "pottery", "wares", "sherd", "sherds", "typology", "types"},
    "pithouse": {"pithouse", "architecture", "household", "settlement"},
}


def extract_used_citation_ids(text: str) -> list[str]:
    seen = set()
    out: list[str] = []
    for match in re.findall(r"\[(C\d+)\]", text or ""):
        if match not in seen:
            seen.add(match)
            out.append(match)
    return out


def _normalize_tokens(text: str) -> list[str]:
    return [
        tok
        for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]+", (text or "").lower())
        if len(tok) >= 3 and tok not in STOPWORDS
    ]


def build_context_with_citations(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    citations: list[dict[str, Any]] = []
    parts: list[str] = []
    for idx, row in enumerate(rows, start=1):
        cid = f"C{idx}"
        citation = {
            "citation_id": cid,
            "article_id": row.get("article_id"),
            "article_title": row.get("article_title"),
            "article_year": row.get("article_year"),
            "authors": row.get("authors") or ([row.get("author")] if row.get("author") else []),
            "chunk_id": row.get("chunk_id"),
            "page_start": row.get("page_start"),
            "page_end": row.get("page_end"),
            "citekey": row.get("article_citekey"),
            "doi": row.get("article_doi"),
            "source_path": row.get("article_source_path"),
            "text": row.get("chunk_text"),
        }
        citations.append(citation)
        parts.append(
            "\n".join(
                [
                    f"[{cid}]",
                    f"Title: {citation['article_title']}",
                    f"Year: {citation['article_year']}",
                    f"Authors: {', '.join(citation['authors']) if citation['authors'] else 'Unknown'}",
                    f"Citekey: {citation['citekey']}",
                    f"DOI: {citation['doi']}",
                    f"Pages: {citation['page_start']}-{citation['page_end']}",
                    f"Chunk: {citation['chunk_id']}",
                    f"Text: {citation['text']}",
                ]
            )
        )
    return "\n\n".join(parts), citations


def _question_anchor_families(question: str) -> dict[str, set[str]]:
    tokens = set(_normalize_tokens(question))
    families: dict[str, set[str]] = {}
    culture_hits = {culture for culture in ARCHAEOLOGY_CULTURES if culture in tokens}
    if culture_hits:
        families["culture"] = culture_hits
    place_hits = {term for term in DOMAIN_PLACE_TERMS if term in tokens}
    if place_hits:
        families["place"] = place_hits
    artifact_hits = set()
    for hints in ARTIFACT_FAMILY_TERMS.values():
        if tokens & hints:
            artifact_hits |= (tokens & hints)
    if artifact_hits:
        families["artifact"] = artifact_hits
    return families


def _row_anchor_matches(question: str, haystack: str) -> tuple[dict[str, list[str]], int]:
    families = _question_anchor_families(question)
    hay_tokens = set(_normalize_tokens(haystack))
    matched: dict[str, list[str]] = {}
    for name, terms in families.items():
        hits = sorted(hay_tokens & terms)
        if hits:
            matched[name] = hits
    return matched, len(matched)


def _assess_relevance(question: str, citations: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    question_tokens = set(_normalize_tokens(question))
    anchor_families = _question_anchor_families(question)
    relevant: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for citation in citations:
        haystack = " ".join(
            [
                str(citation.get("article_title") or ""),
                " ".join(citation.get("authors") or []),
                str(citation.get("text") or ""),
            ]
        )
        hay_tokens = set(_normalize_tokens(haystack))
        overlap = sorted(question_tokens & hay_tokens)
        anchor_matches, anchor_family_count = _row_anchor_matches(question, haystack)
        minimum_overlap = 1 if not anchor_families else 2
        minimum_anchor_families = 0 if not anchor_families else (1 if len(anchor_families) == 1 else 2)
        usable = len(overlap) >= minimum_overlap and anchor_family_count >= minimum_anchor_families
        assessed = dict(citation)
        assessed["relevance_overlap_terms"] = overlap
        assessed["relevance_anchor_matches"] = anchor_matches
        assessed["relevance_score"] = len(overlap) + (2 * anchor_family_count)
        if usable:
            relevant.append(assessed)
        else:
            excluded.append(assessed)
    if not citations:
        summary = "No retrieved evidence was available to assess for relevance."
    elif relevant:
        summary = f"Used {len(relevant)} of {len(citations)} retrieved results after hard relevance gating before synthesis."
    else:
        summary = "None of the retrieved results passed hard relevance gating for this question."
    return relevant, excluded, summary


def gate_rows_for_synthesis(question: str, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    _context, citations = build_context_with_citations(rows)
    relevant, excluded, summary = _assess_relevance(question, citations)
    row_by_citation = {f"C{idx}": row for idx, row in enumerate(rows, start=1)}
    usable_rows = [row_by_citation[citation["citation_id"]] for citation in relevant if citation["citation_id"] in row_by_citation]
    excluded_rows = [row_by_citation[citation["citation_id"]] for citation in excluded if citation["citation_id"] in row_by_citation]
    return usable_rows, excluded_rows, summary


ARCHAEOLOGY_CULTURES = {
    "hohokam": {
        "region": ["arizona", "sonoran", "southwestern"],
        "period": ["prehistoric", "classic", "sedentary"],
    },
    "anasazi": {
        "region": ["southwestern", "four", "corners"],
        "period": ["ancestral", "pueblo", "prehistoric"],
    },
    "mogollon": {
        "region": ["southwestern", "new", "mexico", "arizona"],
        "period": ["mimbres", "prehistoric"],
    },
    "fremont": {
        "region": ["utah", "intermountain"],
        "period": ["prehistoric", "formative"],
    },
}

ARCHAEOLOGY_OBJECT_TERMS = {
    "projectile": ["point", "points", "typology", "arrowhead", "arrowheads", "dart", "darts", "biface", "bifaces", "typological"],
    "points": ["projectile", "point", "typology", "dart", "arrow", "typological"],
    "ceramic": ["pottery", "wares", "typology", "type", "types"],
    "pottery": ["ceramic", "wares", "typology", "type", "types"],
    "pithouse": ["architecture", "household", "settlement"],
}


def _clean_query_segment(value: str) -> str:
    cleaned = re.sub(r"\b(and|or|not)\b", " ", value or "", flags=re.IGNORECASE)
    cleaned = re.sub(r"[(){}\[\]|:]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _dedupe_query_terms(parts: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for part in parts:
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", part):
            norm = token.lower()
            if norm in seen:
                continue
            seen.add(norm)
            ordered.append(token)
    return " ".join(ordered)


def _archaeology_query_terms(tokens: list[str]) -> list[str]:
    token_set = {tok.lower() for tok in tokens}
    extras: list[str] = []
    if token_set & set(ARCHAEOLOGY_CULTURES):
        if token_set & {"projectile", "point", "points", "arrowhead", "arrowheads", "dart", "darts"}:
            extras.extend(["typology", "lithic"])
        elif token_set & {"ceramic", "pottery", "sherd", "sherds"}:
            extras.extend(["ceramic", "typology"])
    for culture, hints in ARCHAEOLOGY_CULTURES.items():
        if culture in token_set:
            extras.extend(hints.get("region", []))
            extras.extend(hints.get("period", []))
    for key, hints in ARCHAEOLOGY_OBJECT_TERMS.items():
        if key in token_set:
            extras.extend(hints)
    return [term for term in extras if term.lower() not in token_set]


def _directive_to_compact_query(text: str, question: str) -> str:
    line = (text.splitlines()[0] if text else "").strip().strip('"').strip("'")
    line = re.sub(r"\s+", " ", line)

    def _extract(field: str) -> str:
        match = re.search(rf"{field}\s*:\s*([^|]+)", line, flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    authors = _extract("authors")
    years = _extract("years")
    title_terms = _extract("title_terms")
    content_terms = _extract("content_terms")
    parts = []
    for value in (authors, years, title_terms, content_terms):
        if not value or value.lower() == "none":
            continue
        cleaned = _clean_query_segment(value)
        if cleaned:
            parts.append(cleaned)
    if parts:
        compact = _dedupe_query_terms(parts)
        return compact or question
    fallback = _clean_query_segment(line)
    compact = _dedupe_query_terms([fallback]) if fallback else ""
    return compact or question


def _rewrite_is_sane(question: str, rewritten: str) -> bool:
    original_tokens = set(_normalize_tokens(question))
    rewritten_tokens = set(_normalize_tokens(rewritten))
    if not rewritten_tokens:
        return False
    if rewritten_tokens <= REWRITE_GENERIC_TOKENS:
        return False
    anchor_families = _question_anchor_families(question)
    preserved_anchors = sum(1 for terms in anchor_families.values() if rewritten_tokens & terms)
    if anchor_families and preserved_anchors < len(anchor_families):
        return False
    critical_original = {
        token
        for token in original_tokens
        if token not in REWRITE_GENERIC_TOKENS
        and (
            token in DOMAIN_PLACE_TERMS
            or token in ARCHAEOLOGY_CULTURES
            or any(token in hints for hints in ARTIFACT_FAMILY_TERMS.values())
        )
    }
    if critical_original and len(critical_original & rewritten_tokens) < max(1, min(2, len(critical_original))):
        return False
    if len(rewritten_tokens) < max(2, min(3, len(original_tokens))):
        return False
    return True


def _deterministic_query_directive(question: str) -> str:
    text = re.sub(r"[^A-Za-z0-9\- ]+", " ", question or "")
    years = " ".join(re.findall(r"\b(?:19|20)\d{2}\b", text)) or "none"
    tokens = [
        tok
        for tok in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
        if tok.lower()
        not in {
            "what",
            "which",
            "when",
            "where",
            "who",
            "whom",
            "whose",
            "why",
            "how",
            "did",
            "does",
            "do",
            "the",
            "a",
            "an",
            "in",
            "on",
            "for",
            "of",
            "to",
            "about",
            "argue",
            "says",
            "say",
        }
    ]
    archaeology_terms = _archaeology_query_terms(tokens)
    title_terms = " ".join(tokens[:4]) or "none"
    content_terms = " ".join(tokens[4:10] + archaeology_terms[:12]) or "none"
    authors = " ".join(tok for tok in tokens if tok[:1].isupper()) or "none"
    return f"authors: {authors} | years: {years} | title_terms: {title_terms} | content_terms: {content_terms}"


def preprocess_search_query(
    question: str,
    model: str | None = None,
    backend: str | None = None,
    settings: Settings | None = None,
) -> str:
    _ = model, backend, settings
    text = _deterministic_query_directive(question)
    compact = _directive_to_compact_query(text, question)
    if _rewrite_is_sane(question, compact):
        return compact
    return question.strip() or compact


def _deterministic_grounded_answer(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    context_text, citations = build_context_with_citations(rows)
    relevant, excluded, relevance_summary = _assess_relevance(question, citations)
    if not citations:
        return {
            "answer": "Unable to produce a grounded answer because no supporting RAG context was found for this question.",
            "used_citations": [],
            "all_citations": [],
            "relevant_citations": [],
            "excluded_citations": [],
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "no_context",
            "fallback_reason": "no_retrieved_context",
            "context": context_text,
            "evidence_snippets": [],
            "relevance_summary": relevance_summary,
        }

    if not relevant:
        return {
            "answer": "None of the retrieved evidence appears relevant enough to answer this question.",
            "used_citations": [],
            "all_citations": citations,
            "relevant_citations": [],
            "excluded_citations": excluded,
            "citation_enforced": True,
            "method": "deterministic_fallback",
            "synthesis_status": "irrelevant_context",
            "fallback_reason": "no_relevant_evidence",
            "context": context_text,
            "evidence_snippets": [],
            "relevance_summary": relevance_summary,
        }

    evidence_snippets = []
    for citation in relevant[: min(3, len(relevant))]:
        text = (citation.get("text") or "").strip()
        if text:
            evidence_snippets.append(f"[{citation['citation_id']}] {text}")
    return {
        "answer": (
            "Retrieved context included some relevant evidence, but synthesis could not be completed reliably. "
            "Use the relevant citations and evidence snippets below instead of the irrelevant retrieved items."
        ),
        "used_citations": relevant,
        "all_citations": citations,
        "relevant_citations": relevant,
        "excluded_citations": excluded,
        "citation_enforced": True,
        "method": "deterministic_fallback",
        "synthesis_status": "failed",
        "fallback_reason": "synthesis_unavailable",
        "context": context_text,
        "evidence_snippets": evidence_snippets,
        "relevance_summary": relevance_summary,
    }


def ask_grounded(
    question: str,
    rows: list[dict[str, Any]],
    model: str | None = None,
    enforce_citations: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    _ = model, enforce_citations, settings
    return _deterministic_grounded_answer(question, rows)


def ask_openai_grounded(
    question: str,
    rows: list[dict[str, Any]],
    model: str | None = None,
    enforce_citations: bool = True,
) -> dict[str, Any]:
    return ask_grounded(question, rows, model=model, enforce_citations=enforce_citations)
