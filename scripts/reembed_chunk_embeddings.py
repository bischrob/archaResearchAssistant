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
    parser = argparse.ArgumentParser(description="Re-embed existing chunk nodes in controlled batches.")
    parser.add_argument("--batch-size", type=int, default=32, help="Number of chunks per embedding/update batch")
    parser.add_argument("--limit", type=int, default=32, help="Maximum number of chunks to process this run")
    parser.add_argument("--offset", type=int, default=0, help="Chunk offset for batched continuation")
    parser.add_argument(
        "--validate-query",
        default="",
        help="Optional retrieval query to run after the batch completes",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read and encode the target batch without writing embeddings back",
    )
    return parser.parse_args()


def iter_target_chunks(store: GraphStore, *, limit: int, offset: int) -> list[dict]:
    with store.driver.session() as session:
        rows = session.run(
            """
            MATCH (c:Chunk)
            RETURN c.id AS chunk_id, c.text AS chunk_text
            ORDER BY c.id ASC
            SKIP $offset
            LIMIT $limit
            """,
            offset=max(0, int(offset)),
            limit=max(1, int(limit)),
        )
        return [dict(r) for r in rows]


def write_embeddings(store: GraphStore, rows: list[dict]) -> None:
    payload = [{"id": row["chunk_id"], "embedding": row["embedding"]} for row in rows]
    if not payload:
        return
    with store.driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (c:Chunk {id: row.id})
            SET c.embedding = row.embedding
            """,
            rows=payload,
        )


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
        target_rows = iter_target_chunks(store, limit=args.limit, offset=args.offset)
        if not target_rows:
            print("No chunks found for the requested batch.")
            return

        batch_size = max(1, int(args.batch_size))
        processed = 0
        for start in range(0, len(target_rows), batch_size):
            batch = target_rows[start : start + batch_size]
            texts = [str(row.get("chunk_text") or "") for row in batch]
            embeddings = store.embedder.encode(texts)
            for row, emb in zip(batch, embeddings):
                row["embedding"] = emb
            if not args.dry_run:
                write_embeddings(store, batch)
            processed += len(batch)
            print(f"Processed batch {start // batch_size + 1}: {processed}/{len(target_rows)} chunks")

        if args.validate_query:
            rows = contextual_retrieve(store, query=args.validate_query, limit=3)
            print("\nValidation query results:")
            for idx, row in enumerate(rows, start=1):
                print(
                    f"[{idx}] {row.get('article_title')} | chunk={row.get('chunk_id')} | "
                    f"score={row.get('combined_score', row.get('rerank_score', 0.0)):.4f}"
                )
                print((row.get("chunk_text") or "")[:240].replace("\n", " "))
                print()
    finally:
        store.close()


if __name__ == "__main__":
    main()
