#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore
from src.rag.retrieval import contextual_retrieve


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Contextual retrieval from Neo4j RAG graph.")
    parser.add_argument("query", help="Natural language query")
    parser.add_argument("--limit", type=int, default=5, help="Maximum results")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = Settings()
    store = GraphStore(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        embedding_model=settings.embedding_model,
    )
    try:
        rows = contextual_retrieve(store, query=args.query, limit=args.limit)
    finally:
        store.close()

    if not rows:
        print("No results.")
        return

    for idx, row in enumerate(rows, start=1):
        print(f"\n[{idx}] {row['article_title']} ({row.get('article_year')})")
        print(f"Author: {row.get('author')}")
        print(f"Chunk: {row.get('chunk_id')} pages {row.get('page_start')}-{row.get('page_end')}")
        print(f"Score: {row.get('combined_score'):.4f}")
        print(f"Text: {row.get('chunk_text', '')[:450]}...")
        out_refs = [x for x in row.get("cites_out", []) if x]
        in_refs = [x for x in row.get("cited_by", []) if x]
        if out_refs:
            print(f"Cites: {', '.join(out_refs)}")
        if in_refs:
            print(f"Cited by: {', '.join(in_refs)}")


if __name__ == "__main__":
    main()
