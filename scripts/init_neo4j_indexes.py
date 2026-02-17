#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Neo4j schema constraints/indexes.")
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=90,
        help="Maximum time to wait for Neo4j connectivity before failing.",
    )
    parser.add_argument(
        "--retry-interval",
        type=float,
        default=2.0,
        help="Seconds between connectivity retries.",
    )
    return parser.parse_args()


def wait_for_neo4j(store: GraphStore, wait_seconds: int, retry_interval: float) -> None:
    deadline = time.time() + max(1, wait_seconds)
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with store.driver.session() as session:
                session.run("RETURN 1").single()
            return
        except Exception as exc:
            last_error = exc
            time.sleep(max(0.1, retry_interval))
    if last_error is not None:
        raise RuntimeError(f"Neo4j was not reachable within {wait_seconds}s: {last_error}") from last_error
    raise RuntimeError(f"Neo4j was not reachable within {wait_seconds}s.")


def list_schema(store: GraphStore) -> tuple[list[dict], list[dict]]:
    with store.driver.session() as session:
        idx_rows = session.run(
            """
            SHOW INDEXES
            YIELD name, type, entityType, labelsOrTypes, properties, state
            RETURN name, type, entityType, labelsOrTypes, properties, state
            ORDER BY name
            """
        )
        con_rows = session.run(
            """
            SHOW CONSTRAINTS
            YIELD name, type, entityType, labelsOrTypes, properties
            RETURN name, type, entityType, labelsOrTypes, properties
            ORDER BY name
            """
        )
        indexes = [dict(r) for r in idx_rows]
        constraints = [dict(r) for r in con_rows]
    return indexes, constraints


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
        wait_for_neo4j(store, wait_seconds=args.wait_seconds, retry_interval=args.retry_interval)
        store.setup_schema(vector_dimensions=store.embedding_dimension)
        indexes, constraints = list_schema(store)
    finally:
        store.close()

    print(f"Applied schema on {settings.neo4j_uri}")
    print(f"Indexes: {len(indexes)}")
    for row in indexes:
        labels = ",".join(row.get("labelsOrTypes") or [])
        props = ",".join(row.get("properties") or [])
        print(f" - {row['name']} [{row['type']} {row['state']}] ({labels}) ({props})")
    print(f"Constraints: {len(constraints)}")
    for row in constraints:
        labels = ",".join(row.get("labelsOrTypes") or [])
        props = ",".join(row.get("properties") or [])
        print(f" - {row['name']} [{row['type']}] ({labels}) ({props})")


if __name__ == "__main__":
    main()
