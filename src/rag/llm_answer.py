from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .openclaw_agent import invoke_openclaw_agent


def extract_used_citation_ids(text: str) -> list[str]:
    seen = set()
    out: list[str] = []
    for match in re.findall(r"\[(C\d+)\]", text or ""):
        if match not in seen:
            seen.add(match)
            out.append(match)
    return out


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
        cleaned = re.sub(r"\b(and|or|not)\b", " ", value, flags=re.IGNORECASE)
        cleaned = re.sub(r"[(){}\[\]]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            parts.append(cleaned)
    if parts:
        return " ".join(parts)
    fallback = re.sub(r"\b(and|or|not)\b", " ", line, flags=re.IGNORECASE)
    fallback = re.sub(r"[(){}\[\]|:]", " ", fallback)
    fallback = re.sub(r"\s+", " ", fallback).strip()
    return fallback or question


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
    title_terms = " ".join(tokens[:4]) or "none"
    content_terms = " ".join(tokens[4:10]) or "none"
    authors = " ".join(tok for tok in tokens if tok[:1].isupper()) or "none"
    return f"authors: {authors} | years: {years} | title_terms: {title_terms} | content_terms: {content_terms}"


def preprocess_search_query(
    question: str,
    model: str | None = None,
    backend: str | None = None,
    settings: Settings | None = None,
) -> str:
    cfg = settings or Settings()
    selected_backend = (backend or cfg.query_preprocess_backend or "deterministic").strip().lower()
    text = ""
    if selected_backend in {"openclaw", "openclaw_agent", "agent"}:
        try:
            response = invoke_openclaw_agent(
                "query_preprocess",
                {
                    "question": question,
                    "model": model,
                    "instruction": "Rewrite the question into a single retrieval directive line: authors: ... | years: ... | title_terms: ... | content_terms: ...",
                },
                settings=cfg,
                timeout=60,
            )
        except Exception:
            response = None
        if isinstance(response, dict):
            text = str(response.get("directive") or response.get("text") or "").strip()
    if not text:
        text = _deterministic_query_directive(question)
    return _directive_to_compact_query(text, question)


def _deterministic_grounded_answer(question: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    context_text, citations = build_context_with_citations(rows)
    if not citations:
        return {
            "answer": "No supporting RAG context was found for this question.",
            "used_citations": [],
            "all_citations": [],
            "citation_enforced": True,
            "method": "deterministic_fallback",
        }

    used = citations[: min(3, len(citations))]
    snippets = []
    for citation in used:
        text = (citation.get("text") or "").strip()
        if text:
            snippets.append(f"[{citation['citation_id']}] {text}")
    answer = (
        " ".join(snippets)
        if snippets
        else "The retrieved context contains limited evidence for a grounded summary."
    )
    return {
        "answer": answer,
        "used_citations": used,
        "all_citations": citations,
        "citation_enforced": True,
        "method": "deterministic_fallback",
        "context": context_text,
    }


def ask_grounded(
    question: str,
    rows: list[dict[str, Any]],
    model: str | None = None,
    enforce_citations: bool = True,
    settings: Settings | None = None,
) -> dict[str, Any]:
    cfg = settings or Settings()
    fallback = _deterministic_grounded_answer(question, rows)
    try:
        response = invoke_openclaw_agent(
            "grounded_answer",
            {
                "question": question,
                "model": model,
                "enforce_citations": enforce_citations,
                "rows": rows,
                "fallback": fallback,
            },
            settings=cfg,
            timeout=120,
        )
    except Exception as exc:
        fallback["agent_error"] = str(exc)
        return fallback
    if not isinstance(response, dict):
        return fallback
    answer = str(response.get("answer") or response.get("text") or "").strip()
    if not answer:
        return fallback
    all_citations = fallback["all_citations"]
    used_ids = set(extract_used_citation_ids(answer))
    used_citations = [citation for citation in all_citations if citation["citation_id"] in used_ids]
    if enforce_citations and not used_citations:
        return fallback
    return {
        "answer": answer,
        "used_citations": used_citations,
        "all_citations": all_citations,
        "citation_enforced": True,
        "method": "openclaw_agent",
    }


def ask_openai_grounded(
    question: str,
    rows: list[dict[str, Any]],
    model: str | None = None,
    enforce_citations: bool = True,
) -> dict[str, Any]:
    return ask_grounded(question, rows, model=model, enforce_citations=enforce_citations)
