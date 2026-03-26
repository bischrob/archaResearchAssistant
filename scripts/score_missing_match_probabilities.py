#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore


def _norm_text(s: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    d = doi.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d.strip().rstrip(".;,")


def _sim(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _jaccard(a: str, b: str) -> float:
    sa = set(a.split())
    sb = set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _stem(path_str: str | None) -> str:
    raw = (path_str or "").replace("\\", "/")
    base = raw.split("/")[-1]
    if base.lower().endswith(".pdf"):
        base = base[:-4]
    return _norm_text(base)


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"\b(19|20)\d{2}\b", str(value))
    if not m:
        return None
    return int(m.group(0))


def _extract_likely_author_token(source_path: str, article_id: str, title: str) -> str:
    candidate = _stem(source_path) or _norm_text(article_id) or _norm_text(title)
    if not candidate:
        return ""
    toks = candidate.split()
    return toks[0] if toks else ""


@dataclass
class Candidate:
    id: str
    title: str
    year: int | None
    doi: str
    citekey: str
    source_path: str
    author_tokens: set[str]
    ntitle: str


def _load_candidates() -> list[Candidate]:
    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    query = """
    MATCH (a:Article)
    WHERE coalesce(a.zotero_persistent_id, '') <> ''
    OPTIONAL MATCH (p:Author)-[w:WROTE]->(a)
    WITH a, p, w
    ORDER BY w.position ASC
    WITH a, collect(p.name) AS authors
    RETURN a.id AS id,
           a.title AS title,
           a.year AS year,
           a.doi AS doi,
           a.citekey AS citekey,
           a.source_path AS source_path,
           authors
    """
    out: list[Candidate] = []
    try:
        with store.driver.session() as session:
            for r in session.run(query):
                title = str(r.get("title") or "")
                author_tokens: set[str] = set()
                for name in r.get("authors") or []:
                    for t in re.findall(r"[a-z][a-z'-]+", (name or "").lower()):
                        if len(t) >= 3:
                            author_tokens.add(t)
                year = r.get("year")
                try:
                    year = int(year) if year is not None else None
                except Exception:
                    year = None
                out.append(
                    Candidate(
                        id=str(r.get("id") or ""),
                        title=title,
                        year=year,
                        doi=_norm_doi(r.get("doi")),
                        citekey=str(r.get("citekey") or ""),
                        source_path=str(r.get("source_path") or ""),
                        author_tokens=author_tokens,
                        ntitle=_norm_text(title),
                    )
                )
    finally:
        store.close()
    return out


def _score(missing_row: dict[str, str], candidates: list[Candidate]) -> dict:
    m_id = missing_row.get("id") or ""
    m_title = missing_row.get("title") or ""
    m_source = missing_row.get("source_path") or ""
    m_doi = _norm_doi(missing_row.get("doi"))
    m_year = _extract_year(missing_row.get("year")) or _extract_year(m_id) or _extract_year(m_source)
    m_author_tok = _extract_likely_author_token(m_source, m_id, m_title)

    m_ntitle = _norm_text(m_title) or _stem(m_source) or _norm_text(m_id)

    best = None
    second = None
    for c in candidates:
        doi_score = 1.0 if (m_doi and c.doi and m_doi == c.doi) else 0.0
        title_sim = _sim(m_ntitle, c.ntitle)
        title_j = _jaccard(m_ntitle, c.ntitle)

        year_score = 0.0
        if m_year is not None and c.year is not None:
            if m_year == c.year:
                year_score = 1.0
            elif abs(m_year - c.year) == 1:
                year_score = 0.4

        author_score = 0.0
        if m_author_tok:
            if m_author_tok in c.author_tokens:
                author_score = 1.0
            elif m_author_tok in _norm_text(c.id) or m_author_tok in c.ntitle:
                author_score = 0.5

        raw = 0.60 * title_sim + 0.20 * title_j + 0.12 * year_score + 0.08 * author_score
        if doi_score > 0:
            raw = max(raw, 0.98)
        prob = max(0.0, min(1.0, raw))

        record = {
            "candidate_id": c.id,
            "candidate_title": c.title,
            "candidate_year": c.year,
            "candidate_citekey": c.citekey,
            "candidate_source_path": c.source_path,
            "title_similarity": round(title_sim, 4),
            "title_jaccard": round(title_j, 4),
            "year_score": round(year_score, 4),
            "author_score": round(author_score, 4),
            "doi_exact": bool(doi_score),
            "match_probability": round(prob, 4),
        }
        if best is None or record["match_probability"] > best["match_probability"]:
            second = best
            best = record
        elif second is None or record["match_probability"] > second["match_probability"]:
            second = record

    return {
        "missing_id": m_id,
        "missing_title": m_title,
        "missing_year": m_year,
        "missing_doi": m_doi,
        "missing_source_path": m_source,
        "likely_author_token": m_author_tok,
        "best_match": best,
        "second_match": second,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score missing-zotero files against existing identified Neo4j entries.")
    parser.add_argument("--missing-csv", default="logs/neo4j_pdfs_missing_zotero_identifier.csv")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0, help="0 means all rows from offset.")
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.missing_csv).open("r", encoding="utf-8")))
    start = max(0, args.offset)
    end = len(rows) if args.limit <= 0 else min(len(rows), start + args.limit)
    subset = rows[start:end]

    candidates = _load_candidates()
    scored = [_score(r, candidates) for r in subset]

    out = {
        "offset": start,
        "limit": args.limit,
        "row_count": len(subset),
        "scored": scored,
    }
    out_path = Path(args.out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({"out_json": str(out_path), "rows": len(subset)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
