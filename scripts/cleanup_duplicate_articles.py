#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rag.config import Settings
from src.rag.metadata_provider import metadata_title_year_key
from src.rag.neo4j_store import GraphStore


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    normalized = doi.strip().lower()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized)
    return normalized.strip().rstrip(".;,")


@dataclass
class Article:
    id: str
    title: str
    year: int | None
    doi: str
    citekey: str
    source_path: str
    zotero_persistent_id: str
    zotero_item_key: str
    chunk_count: int
    reference_count: int
    in_cites_count: int
    out_cites_count: int

    @property
    def title_year_key(self) -> str | None:
        return metadata_title_year_key({"title": self.title, "year": self.year})


class DSU:
    def __init__(self, nodes: list[str]) -> None:
        self.parent = {n: n for n in nodes}

    def find(self, x: str) -> str:
        p = self.parent[x]
        if p != x:
            self.parent[x] = self.find(p)
        return self.parent[x]

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _load_missing_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8") as f:
        return {row["id"] for row in csv.DictReader(f) if row.get("id")}


def _load_articles(store: GraphStore) -> dict[str, Article]:
    query = """
    MATCH (a:Article)
    CALL {
      WITH a
      OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(:Chunk)
      RETURN count(*) AS chunk_count
    }
    CALL {
      WITH a
      OPTIONAL MATCH (a)-[:CITES_REFERENCE]->(:Reference)
      RETURN count(*) AS reference_count
    }
    CALL {
      WITH a
      OPTIONAL MATCH (:Article)-[c:CITES]->(a)
      RETURN count(c) AS in_cites_count
    }
    CALL {
      WITH a
      OPTIONAL MATCH (a)-[c:CITES]->(:Article)
      RETURN count(c) AS out_cites_count
    }
    RETURN a.id AS id,
           a.title AS title,
           a.year AS year,
           a.doi AS doi,
           a.citekey AS citekey,
           a.source_path AS source_path,
           a.zotero_persistent_id AS zotero_persistent_id,
           a.zotero_item_key AS zotero_item_key,
           chunk_count,
           reference_count,
           in_cites_count,
           out_cites_count
    """
    out: dict[str, Article] = {}
    with store.driver.session() as session:
        for r in session.run(query):
            article_id = str(r.get("id") or "").strip()
            if not article_id:
                continue
            year_val = r.get("year")
            try:
                year_val = int(year_val) if year_val is not None else None
            except Exception:
                year_val = None
            out[article_id] = Article(
                id=article_id,
                title=str(r.get("title") or ""),
                year=year_val,
                doi=str(r.get("doi") or ""),
                citekey=str(r.get("citekey") or ""),
                source_path=str(r.get("source_path") or ""),
                zotero_persistent_id=str(r.get("zotero_persistent_id") or ""),
                zotero_item_key=str(r.get("zotero_item_key") or ""),
                chunk_count=int(r.get("chunk_count") or 0),
                reference_count=int(r.get("reference_count") or 0),
                in_cites_count=int(r.get("in_cites_count") or 0),
                out_cites_count=int(r.get("out_cites_count") or 0),
            )
    return out


def _candidate_groups(articles: dict[str, Article], missing_ids: set[str]) -> list[set[str]]:
    ids = set(articles.keys())
    dsu = DSU(list(ids))

    by_doi: dict[str, list[str]] = defaultdict(list)
    by_ty: dict[str, list[str]] = defaultdict(list)
    for a in articles.values():
        doi = _normalize_doi(a.doi)
        if doi:
            by_doi[doi].append(a.id)
        ty = (a.title_year_key or "").lower()
        if ty:
            by_ty[ty].append(a.id)

    for group in by_doi.values():
        if len(group) <= 1:
            continue
        if not any(g in missing_ids for g in group):
            continue
        head = group[0]
        for g in group[1:]:
            dsu.union(head, g)

    for group in by_ty.values():
        if len(group) <= 1:
            continue
        if not any(g in missing_ids for g in group):
            continue
        head = group[0]
        for g in group[1:]:
            dsu.union(head, g)

    grouped: dict[str, set[str]] = defaultdict(set)
    for i in ids:
        grouped[dsu.find(i)].add(i)

    return [g for g in grouped.values() if len(g) > 1 and any(x in missing_ids for x in g)]


def _rank_key(a: Article, missing_ids: set[str]) -> tuple:
    # Higher tuple wins.
    source_lower = a.source_path.lower()
    from_zotero_storage = int("/zotero/storage/" in source_lower or "\\zotero\\storage\\" in source_lower)
    not_missing = int(a.id not in missing_ids)
    return (
        int(bool(a.zotero_persistent_id)),
        int(bool(a.zotero_item_key)),
        not_missing,
        int(bool(a.citekey)),
        int(bool(_normalize_doi(a.doi))),
        from_zotero_storage,
        a.chunk_count,
        a.reference_count,
        a.in_cites_count + a.out_cites_count,
        -len(a.id),  # shorter id preferred when otherwise tied
    )


def _choose_keep(group: set[str], articles: dict[str, Article], missing_ids: set[str]) -> str:
    members = [articles[g] for g in group]
    members.sort(key=lambda a: _rank_key(a, missing_ids), reverse=True)
    return members[0].id


def _merge_one(store: GraphStore, keep_id: str, drop_id: str) -> None:
    with store.driver.session() as session:
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            SET keep.doi = CASE WHEN coalesce(keep.doi, '') = '' THEN drop.doi ELSE keep.doi END,
                keep.citekey = CASE WHEN coalesce(keep.citekey, '') = '' THEN drop.citekey ELSE keep.citekey END,
                keep.zotero_item_key = CASE WHEN coalesce(keep.zotero_item_key, '') = '' THEN drop.zotero_item_key ELSE keep.zotero_item_key END,
                keep.zotero_attachment_key = CASE WHEN coalesce(keep.zotero_attachment_key, '') = '' THEN drop.zotero_attachment_key ELSE keep.zotero_attachment_key END,
                keep.zotero_library_id = CASE WHEN coalesce(toString(keep.zotero_library_id), '') = '' THEN drop.zotero_library_id ELSE keep.zotero_library_id END,
                keep.zotero_persistent_id = CASE WHEN coalesce(keep.zotero_persistent_id, '') = '' THEN drop.zotero_persistent_id ELSE keep.zotero_persistent_id END,
                keep.source_path = CASE WHEN coalesce(keep.source_path, '') = '' THEN drop.source_path ELSE keep.source_path END
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            OPTIONAL MATCH (p:Author)-[w:WROTE]->(drop)
            WITH keep, p, w
            WHERE p IS NOT NULL AND w IS NOT NULL
            MERGE (p)-[w2:WROTE]->(keep)
            ON CREATE SET w2.position = w.position
            ON MATCH SET w2.position = CASE
              WHEN w2.position IS NULL THEN w.position
              WHEN w.position IS NULL THEN w2.position
              WHEN w.position < w2.position THEN w.position
              ELSE w2.position
            END
            DELETE w
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            OPTIONAL MATCH (c:Chunk)-[inRel:IN_ARTICLE]->(drop)
            WITH keep, c, inRel
            WHERE c IS NOT NULL AND inRel IS NOT NULL
            MERGE (c)-[:IN_ARTICLE]->(keep)
            DELETE inRel
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            OPTIONAL MATCH (drop)-[cr:CITES_REFERENCE]->(r:Reference)
            WITH keep, r, cr
            WHERE r IS NOT NULL AND cr IS NOT NULL
            MERGE (keep)-[:CITES_REFERENCE]->(r)
            DELETE cr
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            OPTIONAL MATCH (drop)-[co:CITES]->(dst:Article)
            WITH keep, dst, co
            WHERE dst IS NOT NULL AND co IS NOT NULL
            MERGE (keep)-[:CITES]->(dst)
            DELETE co
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            OPTIONAL MATCH (src:Article)-[ci:CITES]->(drop)
            WITH keep, src, ci
            WHERE src IS NOT NULL AND ci IS NOT NULL
            MERGE (src)-[:CITES]->(keep)
            DELETE ci
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        )
        session.run(
            """
            MATCH (drop:Article {id: $drop_id})
            DETACH DELETE drop
            """,
            drop_id=drop_id,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup duplicate Article nodes using heuristic canonical selection.")
    parser.add_argument(
        "--missing-csv",
        default="logs/neo4j_pdfs_missing_zotero_identifier.csv",
        help="CSV with missing-zotero articles used to scope duplicate cleanup.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    parser.add_argument(
        "--report-json",
        default="logs/duplicate_cleanup_report.json",
        help="Output JSON report path.",
    )
    args = parser.parse_args()

    missing_path = Path(args.missing_csv)
    if not missing_path.exists():
        raise SystemExit(f"Missing CSV not found: {missing_path}")
    missing_ids = _load_missing_ids(missing_path)

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        articles = _load_articles(store)
        groups = _candidate_groups(articles, missing_ids)

        actions: list[dict[str, Any]] = []
        for g in groups:
            keep_id = _choose_keep(g, articles, missing_ids)
            drop_ids = sorted(x for x in g if x != keep_id)
            if not drop_ids:
                continue
            actions.append(
                {
                    "group_size": len(g),
                    "keep_id": keep_id,
                    "drop_ids": drop_ids,
                    "group_ids": sorted(g),
                }
            )

        if args.apply:
            for action in actions:
                keep_id = action["keep_id"]
                for drop_id in action["drop_ids"]:
                    _merge_one(store, keep_id, drop_id)

        # Recompute missing count after apply (or current state for dry-run)
        with store.driver.session() as session:
            row = session.run(
                """
                MATCH (a:Article)
                RETURN count(a) AS total_articles,
                       count(CASE WHEN coalesce(a.source_path,'') ENDS WITH '.pdf' AND coalesce(a.zotero_persistent_id,'')='' THEN 1 END) AS pdf_missing
                """
            ).single()
            total_articles = int(row["total_articles"])
            pdf_missing = int(row["pdf_missing"])
    finally:
        store.close()

    dropped_total = sum(len(a["drop_ids"]) for a in actions)
    report = {
        "apply": bool(args.apply),
        "scoped_missing_ids": len(missing_ids),
        "duplicate_groups_found": len(actions),
        "articles_to_drop": dropped_total,
        "post_total_articles": total_articles,
        "post_pdf_missing_without_zotero_id": pdf_missing,
        "actions_sample": actions[:50],
    }

    report_path = Path(args.report_json)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    print(f"Wrote {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
