#!/usr/bin/env python
from __future__ import annotations

import argparse
import os

from neo4j import GraphDatabase


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Review and optionally delete isolated Neo4j Author nodes.")
    parser.add_argument("--neo4j-uri", default=_env("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=_env("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=_env("NEO4J_PASSWORD", ""))
    parser.add_argument("--limit", type=int, default=200, help="Max sample rows to print in preview mode.")
    parser.add_argument("--apply", action="store_true", help="Actually delete isolated authors.")
    return parser


def _preview(session, limit: int) -> tuple[int, list[dict]]:
    count = session.run(
        """
        MATCH (a:Author)
        WHERE NOT (a)--()
        RETURN count(a) AS c
        """
    ).single()["c"]
    rows = list(
        session.run(
            """
            MATCH (a:Author)
            WHERE NOT (a)--()
            RETURN a.name AS name, a.name_norm AS name_norm, elementId(a) AS element_id
            ORDER BY a.name_norm ASC
            LIMIT $limit
            """,
            limit=max(1, int(limit)),
        )
    )
    return int(count or 0), [dict(row) for row in rows]


def _delete(session) -> int:
    row = session.run(
        """
        MATCH (a:Author)
        WHERE NOT (a)--()
        WITH collect(a) AS doomed
        FOREACH (a IN doomed | DELETE a)
        RETURN size(doomed) AS deleted
        """
    ).single()
    return int((row or {}).get("deleted") or 0)


def main() -> int:
    args = _build_parser().parse_args()
    if not args.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD is required.")

    with GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_password)) as driver:
        with driver.session() as session:
            if args.apply:
                deleted = _delete(session)
                print(f"deleted={deleted}")
                return 0

            total, rows = _preview(session, args.limit)
            print(f"isolated_author_count={total}")
            for row in rows:
                print(
                    f"name={row.get('name')}\t"
                    f"name_norm={row.get('name_norm')}\t"
                    f"element_id={row.get('element_id')}"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
