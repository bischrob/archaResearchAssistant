#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore


def _merge_one(store: GraphStore, keep_id: str, drop_id: str) -> bool:
    with store.driver.session() as session:
        exists = session.run(
            """
            MATCH (keep:Article {id: $keep_id})
            MATCH (drop:Article {id: $drop_id})
            RETURN count(*) AS c
            """,
            keep_id=keep_id,
            drop_id=drop_id,
        ).single()
        if not exists or int(exists["c"]) == 0:
            return False

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
    return True


def _remaining_missing_pdf_count(store: GraphStore) -> int:
    with store.driver.session() as session:
        row = session.run(
            """
            MATCH (a:Article)
            WHERE coalesce(a.source_path, '') ENDS WITH '.pdf'
              AND coalesce(a.zotero_persistent_id, '') = ''
            RETURN count(a) AS c
            """
        ).single()
        return int(row["c"]) if row else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge missing-zotero entries into probable existing entries above a probability threshold.")
    parser.add_argument("--matches-xlsx", default="logs/missing_zotero_match_probabilities.xlsx")
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--out-hist-png", default="logs/missing_zotero_low_probability_histogram.png")
    parser.add_argument("--out-low-csv", default="logs/missing_zotero_low_probability_values.csv")
    parser.add_argument("--out-report-json", default="logs/missing_zotero_probabilistic_merge_report.json")
    args = parser.parse_args()

    df = pd.read_excel(args.matches_xlsx, sheet_name="matches")
    df = df[(df["missing_id"].notna()) & (df["best_candidate_id"].notna())]
    df = df[df["missing_id"] != df["best_candidate_id"]].copy()
    df["best_match_probability"] = pd.to_numeric(df["best_match_probability"], errors="coerce").fillna(0.0)

    to_merge = df[df["best_match_probability"] > args.threshold].copy()
    low = df[df["best_match_probability"] < args.threshold].copy()

    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    merged = 0
    skipped = 0
    failures: list[dict] = []
    try:
        for _, row in to_merge.iterrows():
            keep_id = str(row["best_candidate_id"]).strip()
            drop_id = str(row["missing_id"]).strip()
            if not keep_id or not drop_id or keep_id == drop_id:
                skipped += 1
                continue
            try:
                ok = _merge_one(store, keep_id=keep_id, drop_id=drop_id)
                if ok:
                    merged += 1
                else:
                    skipped += 1
            except Exception as exc:
                failures.append(
                    {
                        "missing_id": drop_id,
                        "best_candidate_id": keep_id,
                        "error": str(exc),
                    }
                )
    finally:
        remaining_missing = _remaining_missing_pdf_count(store)
        store.close()

    low_path = Path(args.out_low_csv)
    low_path.parent.mkdir(parents=True, exist_ok=True)
    low[["missing_id", "missing_title", "best_match_probability"]].to_csv(low_path, index=False)

    hist_path = Path(args.out_hist_png)
    hist_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(8, 5))
    vals = low["best_match_probability"].astype(float).tolist()
    plt.hist(vals, bins=20, edgecolor="black")
    plt.title(f"Low-Category Match Probabilities (< {args.threshold})")
    plt.xlabel("Best Match Probability")
    plt.ylabel("Count")
    plt.tight_layout()
    plt.savefig(hist_path, dpi=160)
    plt.close()

    report = {
        "threshold": args.threshold,
        "candidates_total": int(len(df)),
        "merge_candidates": int(len(to_merge)),
        "low_category_count": int(len(low)),
        "merged": merged,
        "skipped": skipped,
        "failures": failures,
        "remaining_missing_pdf_without_zotero_persistent_id": remaining_missing,
        "histogram_png": str(hist_path),
        "low_values_csv": str(low_path),
    }
    out_report = Path(args.out_report_json)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
