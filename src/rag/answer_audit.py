from __future__ import annotations

import re
from typing import Any

from .pdf_processing import STOPWORDS


def _content_tokens(text: str) -> set[str]:
    toks = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", (text or "").lower())
    return {t for t in toks if t not in STOPWORDS and len(t) > 2}


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return [p.strip() for p in parts if p.strip()]


def audit_answer_support(answer: str, citations: list[dict[str, Any]]) -> dict[str, Any]:
    cited_text = " ".join((c.get("text") or "") for c in citations)
    cited_tokens = _content_tokens(cited_text)
    sentences = _split_sentences(answer)
    unsupported: list[str] = []
    supported = 0

    for sent in sentences:
        st = _content_tokens(sent)
        if not st:
            continue
        overlap = len(st & cited_tokens)
        if overlap == 0:
            unsupported.append(sent)
        else:
            supported += 1

    total = max(1, supported + len(unsupported))
    unsupported_ratio = len(unsupported) / total
    no_citations_penalty = 0.25 if not citations else 0.0
    risk = min(1.0, unsupported_ratio + no_citations_penalty)
    if risk < 0.25:
        label = "low"
    elif risk < 0.6:
        label = "medium"
    else:
        label = "high"

    return {
        "risk_score": round(risk, 3),
        "risk_label": label,
        "unsupported_sentences": unsupported[:20],
        "supported_sentence_count": supported,
        "unsupported_sentence_count": len(unsupported),
    }

