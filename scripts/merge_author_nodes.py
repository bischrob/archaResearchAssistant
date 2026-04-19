di#!/usr/bin/env python
from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass

from neo4j import GraphDatabase


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _normalize_name(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z]+", (value or "").lower())


@dataclass(frozen=True)
class AuthorRow:
    name: str
    name_norm: str
    works: int


@dataclass(frozen=True)
class CandidateMatch:
    kind: str
    source: AuthorRow
    target: AuthorRow
    score: float
    rationale: str


def _candidate_matches(rows: list[AuthorRow]) -> list[CandidateMatch]:
    out: list[CandidateMatch] = []
    for source in rows:
        source_tokens = _tokens(source.name_norm)
        if not source_tokens:
            continue
        for target in rows:
            if source.name_norm == target.name_norm:
                continue
            target_tokens = _tokens(target.name_norm)
            if not target_tokens:
                continue
            if len(source_tokens) >= len(target_tokens):
                continue
            if source.works > target.works:
                continue

            source_set = set(source_tokens)
            target_set = set(target_tokens)
            if not source_set < target_set:
                continue

            kind = ""
            score = 0.0
            rationale = ""
            if len(source_tokens) == 1 and source_tokens[0] == target_tokens[-1]:
                kind = "surname_only"
                score = 0.95
                rationale = "single-token surname matches target surname"
            elif len(source_tokens) == 1 and source_tokens[0] == target_tokens[0]:
                kind = "first_name_only"
                score = 0.60
                rationale = "single-token first name matches target first name"
            elif source_tokens[-1] == target_tokens[-1]:
                kind = "subset_same_surname"
                score = 0.88
                rationale = "source tokens are a strict subset and share surname"
            else:
                continue

            out.append(CandidateMatch(kind=kind, source=source, target=target, score=score, rationale=rationale))

    deduped: dict[tuple[str, str], CandidateMatch] = {}
    for match in out:
        key = (match.source.name_norm, match.target.name_norm)
        prior = deduped.get(key)
        if prior is None or match.score > prior.score:
            deduped[key] = match
    return sorted(
        deduped.values(),
        key=lambda m: (-m.score, -m.target.works, m.source.name_norm, m.target.name_norm),
    )


def _load_authors(uri: str, user: str, password: str) -> list[AuthorRow]:
    query = """
    MATCH (a:Author)
    OPTIONAL MATCH (a)-[:WROTE]->(w)
    RETURN a.name AS name, a.name_norm AS name_norm, count(w) AS works
    ORDER BY works DESC, name_norm ASC
    """
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session() as session:
            return [
                AuthorRow(
                    name=str(row["name"] or row["name_norm"] or ""),
                    name_norm=str(row["name_norm"] or ""),
                    works=int(row["works"] or 0),
                )
                for row in session.run(query)
                if str(row["name_norm"] or "").strip()
            ]


def _merge_authors(
    uri: str,
    user: str,
    password: str,
    *,
    source_name_norm: str,
    target_name_norm: str,
    dry_run: bool,
) -> dict:
    query = """
    MATCH (src:Author {name_norm: $source_name_norm})
    MATCH (dst:Author {name_norm: $target_name_norm})
    OPTIONAL MATCH (src)-[:WROTE]->(article:Article)
    WITH src, dst, collect(DISTINCT article) AS articles
    OPTIONAL MATCH (src)-[:WROTE]->(ref:Reference)
    WITH src, dst, articles, collect(DISTINCT ref) AS refs
    RETURN
      src.name AS source_name,
      src.name_norm AS source_name_norm,
      dst.name AS target_name,
      dst.name_norm AS target_name_norm,
      size([x IN articles WHERE x IS NOT NULL]) AS article_links,
      size([x IN refs WHERE x IS NOT NULL]) AS reference_links
    """
    write_query = """
    MATCH (src:Author {name_norm: $source_name_norm})
    MATCH (dst:Author {name_norm: $target_name_norm})
    OPTIONAL MATCH (src)-[:WROTE]->(article:Article)
    WITH src, dst, collect(DISTINCT article) AS articles
    OPTIONAL MATCH (src)-[:WROTE]->(ref:Reference)
    WITH src, dst, articles, collect(DISTINCT ref) AS refs
    FOREACH (article IN [x IN articles WHERE x IS NOT NULL] |
      MERGE (dst)-[:WROTE]->(article)
    )
    FOREACH (ref IN [x IN refs WHERE x IS NOT NULL] |
      MERGE (dst)-[:WROTE]->(ref)
    )
    DETACH DELETE src
    RETURN
      dst.name AS target_name,
      dst.name_norm AS target_name_norm,
      size([x IN articles WHERE x IS NOT NULL]) AS moved_article_links,
      size([x IN refs WHERE x IS NOT NULL]) AS moved_reference_links
    """
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session() as session:
            preview = session.run(
                query,
                source_name_norm=source_name_norm,
                target_name_norm=target_name_norm,
            ).single()
            if preview is None:
                raise SystemExit("Source or target author node was not found.")
            payload = dict(preview)
            payload["dry_run"] = dry_run
            if dry_run:
                return payload
            result = session.execute_write(
                lambda tx: tx.run(
                    write_query,
                    source_name_norm=source_name_norm,
                    target_name_norm=target_name_norm,
                ).single()
            )
            if result is None:
                raise SystemExit("Author merge failed.")
            out = dict(result)
            out["dry_run"] = False
            return out


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and merge likely duplicate Neo4j Author nodes.")
    parser.add_argument("--neo4j-uri", default=_env("NEO4J_URI", "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=_env("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-password", default=_env("NEO4J_PASSWORD", ""))
    sub = parser.add_subparsers(dest="command", required=True)

    candidates = sub.add_parser("candidates", help="List likely duplicate author-name pairs.")
    candidates.add_argument("--min-score", type=float, default=0.85)
    candidates.add_argument("--limit", type=int, default=50)

    merge = sub.add_parser("merge", help="Merge one Author node into another.")
    merge.add_argument("--source", required=True, help="Source author name or name_norm to merge away.")
    merge.add_argument("--target", required=True, help="Target canonical author name or name_norm to keep.")
    merge.add_argument("--apply", action="store_true", help="Actually write the merge. Default is dry run.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    if not args.neo4j_password:
        raise SystemExit("NEO4J_PASSWORD is required.")

    if args.command == "candidates":
        rows = _load_authors(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        matches = [
            match for match in _candidate_matches(rows)
            if match.score >= float(args.min_score)
        ][: max(1, int(args.limit))]
        for match in matches:
            print(
                f"{match.score:.2f}\t{match.kind}\t"
                f"{match.source.name} [{match.source.works}] -> "
                f"{match.target.name} [{match.target.works}]\t{match.rationale}"
            )
        return 0

    if args.command == "merge":
        source_name_norm = _normalize_name(args.source)
        target_name_norm = _normalize_name(args.target)
        if not source_name_norm or not target_name_norm:
            raise SystemExit("Source and target must normalize to non-empty name_norm values.")
        if source_name_norm == target_name_norm:
            raise SystemExit("Source and target normalize to the same author key; nothing to merge.")
        result = _merge_authors(
            args.neo4j_uri,
            args.neo4j_user,
            args.neo4j_password,
            source_name_norm=source_name_norm,
            target_name_norm=target_name_norm,
            dry_run=not bool(args.apply),
        )
        for key, value in result.items():
            print(f"{key}={value}")
        return 0

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
