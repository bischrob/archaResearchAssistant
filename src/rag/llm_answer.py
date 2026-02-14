from __future__ import annotations

import os
import re
from typing import Any

import requests


def extract_used_citation_ids(text: str) -> list[str]:
    seen = set()
    out: list[str] = []
    for m in re.findall(r"\[(C\d+)\]", text or ""):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def build_context_with_citations(rows: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    citations: list[dict[str, Any]] = []
    parts: list[str] = []
    for idx, r in enumerate(rows, start=1):
        cid = f"C{idx}"
        citation = {
            "citation_id": cid,
            "article_id": r.get("article_id"),
            "article_title": r.get("article_title"),
            "article_year": r.get("article_year"),
            "authors": r.get("authors") or ([r.get("author")] if r.get("author") else []),
            "chunk_id": r.get("chunk_id"),
            "page_start": r.get("page_start"),
            "page_end": r.get("page_end"),
            "citekey": r.get("article_citekey"),
            "doi": r.get("article_doi"),
            "source_path": r.get("article_source_path"),
            "text": r.get("chunk_text"),
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


def ask_openai_grounded(
    question: str,
    rows: list[dict[str, Any]],
    model: str | None = None,
    enforce_citations: bool = True,
) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("OpenAPIKey", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    context_text, citations = build_context_with_citations(rows)
    if not citations:
        return {
            "answer": "No supporting RAG context was found for this question.",
            "used_citations": [],
            "all_citations": [],
        }

    selected_model = (model or os.getenv("OPENAI_MODEL", "gpt-5.1")).strip()
    system = (
        "You are a strict RAG answer assistant. "
        "Only use facts in the provided context blocks. "
        "Never use outside knowledge. "
        "If context is insufficient, explicitly say so. "
        "Cite claims inline using citation IDs exactly like [C1], [C2]."
    )
    user = (
        f"Question:\n{question}\n\n"
        "Context blocks:\n"
        f"{context_text}\n\n"
        "Return a concise answer with inline [C#] citations for every factual claim."
    )

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    answer = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    used_ids = set(extract_used_citation_ids(answer))
    used_citations = [c for c in citations if c["citation_id"] in used_ids]
    citation_enforced = True
    if enforce_citations and not used_citations:
        citation_enforced = False
        answer = (
            "I cannot provide a grounded answer because no valid [C#] citations were produced. "
            "Please refine the question or increase RAG results."
        )

    return {
        "model": selected_model,
        "answer": answer,
        "citation_enforced": citation_enforced,
        "used_citations": used_citations,
        "all_citations": citations,
    }


def preprocess_search_query(question: str, model: str | None = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip() or os.getenv("OpenAPIKey", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    selected_model = (model or os.getenv("OPENAI_MODEL", "gpt-5.1")).strip()
    system = (
        "You rewrite user questions into compact retrieval directives for a Neo4j academic graph. "
        "Graph fields are: Author names, Article title/year, and Chunk text terms. "
        "Do NOT use boolean operators (AND/OR/NOT), parentheses, or pseudo-logic. "
        "Return exactly one line in this format: "
        "authors: <names or none> | years: <years or none> | title_terms: <terms or none> | content_terms: <terms or none>"
    )
    user = (
        f"Question:\n{question}\n\n"
        "Return only the single-line directive in the required format."
    )

    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"OpenAI API error {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    text = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    line = (text.splitlines()[0] if text else "").strip().strip('"').strip("'")
    line = re.sub(r"\s+", " ", line)

    # Convert the directive into a clean retrieval query string optimized for our
    # parser (tokens/years/phrases), while removing boolean syntax.
    def _extract(field: str) -> str:
        m = re.search(rf"{field}\s*:\s*([^|]+)", line, flags=re.IGNORECASE)
        return (m.group(1).strip() if m else "")

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

    # Fallback if model did not follow format.
    fallback = re.sub(r"\b(and|or|not)\b", " ", line, flags=re.IGNORECASE)
    fallback = re.sub(r"[(){}\[\]|:]", " ", fallback)
    fallback = re.sub(r"\s+", " ", fallback).strip()
    return fallback or question
