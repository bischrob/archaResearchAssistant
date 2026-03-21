from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import re

from .config import Settings
from .pdf_processing import ArticleDoc, Keyword
from .qwen_local import decode_qwen_json, generate_with_qwen

KEYWORD_SYSTEM_PROMPT = (
    "You extract retrieval-oriented keywords from academic documents. "
    "Return JSON only with schema {\"keywords\":[{\"value\":\"...\",\"score\":0.0,\"evidence\":\"...\"}]}. "
    "Prefer topical phrases and domain-specific terms. Avoid generic academic filler."
)
STOP = {"study","results","discussion","introduction","conclusion","conclusions","paper","method","methods","analysis","data","article","research","using","used","model"}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _article_source_text(article: ArticleDoc, max_chars: int = 12000) -> str:
    parts = [article.title or ""]
    for chunk in article.chunks or []:
        if getattr(chunk, "section_type", "body") != "body":
            continue
        if chunk.text:
            parts.append(chunk.text)
        if sum(len(x) for x in parts) >= max_chars:
            break
    return "\n\n".join(x for x in parts if x)[:max_chars]


def _heuristic_keywords(article: ArticleDoc, limit: int) -> list[Keyword]:
    counter: Counter[str] = Counter()
    for chunk in article.chunks or []:
        if getattr(chunk, "section_type", "body") != "body":
            continue
        for tok, count in (chunk.token_counts or {}).items():
            key = _norm(tok)
            if len(key) < 4 or key in STOP:
                continue
            counter[key] += int(count)
    out: list[Keyword] = []
    seen: set[str] = set()
    for seed in [article.title, article.journal, article.publisher]:
        if seed:
            norm = _norm(seed)
            if norm and norm not in seen:
                seen.add(norm)
                out.append(Keyword(value=seed.strip(), normalized_value=norm, score=0.95, source="metadata_seed", evidence="metadata"))
    top = counter.most_common(max(limit * 2, 20))
    max_count = top[0][1] if top else 1
    for value, count in top:
        if value in seen:
            continue
        seen.add(value)
        out.append(Keyword(value=value, normalized_value=value, score=min(0.9, 0.2 + (count / max_count)), source="heuristic_tokens", evidence="body_chunk_tokens"))
        if len(out) >= limit:
            break
    return out[:limit]


def extract_keywords(article: ArticleDoc, *, settings: Settings | None = None) -> tuple[list[Keyword], dict]:
    cfg = settings or Settings()
    limit = max(8, min(int(getattr(cfg, "keyword_max_terms", 32)), 80))
    audit = {
        "source_sections": [s.kind for s in (article.sections or [])],
        "body_chunk_count": sum(1 for c in (article.chunks or []) if getattr(c, "section_type", "body") == "body"),
    }
    source_text = _article_source_text(article, max_chars=max(3000, min(int(cfg.qwen_max_input_chars), 14000)))
    parsed = None
    if source_text:
        try:
            raw = generate_with_qwen(
                messages=[
                    {"role": "system", "content": KEYWORD_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Title: {article.title}\n\nDocument excerpt:\n{source_text}\n\nReturn only JSON."},
                ],
                settings=cfg,
                task="citation",
                max_new_tokens=min(900, max(256, int(cfg.qwen_citation_max_new_tokens))),
                temperature=0.0,
            )
            parsed = decode_qwen_json(raw)
        except Exception as exc:
            audit["llm_error"] = str(exc)
    rows = parsed.get("keywords") if isinstance(parsed, dict) else None
    out: list[Keyword] = []
    seen: set[str] = set()
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, str):
                value, score, evidence = row, None, None
            elif isinstance(row, dict):
                value = str(row.get("value") or row.get("keyword") or "").strip()
                score = row.get("score")
                evidence = str(row.get("evidence") or row.get("why") or "").strip() or None
            else:
                continue
            norm = _norm(value)
            if not norm or norm in seen or len(norm) < 3:
                continue
            seen.add(norm)
            out.append(Keyword(value=value, normalized_value=norm, score=float(score) if isinstance(score, (int, float)) else None, source="qwen", evidence=evidence))
            if len(out) >= limit:
                break
    if not out:
        out = _heuristic_keywords(article, limit)
        audit.update({"method": "heuristic" if parsed is None else "heuristic_fallback", "llm_used": parsed is not None})
    else:
        for kw in _heuristic_keywords(article, limit):
            if kw.normalized_value in seen or len(out) >= limit:
                continue
            out.append(kw)
            seen.add(kw.normalized_value)
        audit.update({"method": "qwen_plus_heuristic", "llm_used": True, "llm_keyword_count": len(rows)})
    audit["keyword_count"] = len(out)
    audit["sample"] = [asdict(k) for k in out[:8]]
    return out, audit
