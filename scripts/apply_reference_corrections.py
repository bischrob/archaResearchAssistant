#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import sys

from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.paperpile_metadata import find_metadata_for_pdf, load_paperpile_index
from src.rag.pdf_processing import normalize_title


REFERENCE_KEY_EXPR = """
coalesce(
    nullif(toLower(trim(r.doi)), ''),
    nullif(toLower(trim(r.title_norm)), ''),
    nullif(toLower(trim(r.title_guess)), ''),
    nullif(toLower(trim(r.raw_text)), '')
)
"""

MANUAL_CITES_METHOD = "manual_correction_citekey"


@dataclass
class ParsedCorrections:
    invalid_keys: set[str] = field(default_factory=set)
    merge_by_key: dict[str, str] = field(default_factory=dict)
    total_rows: int = 0
    skipped_rows: int = 0
    conflict_rows: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply reference corrections from corrections/export.csv to Neo4j. "
            "Workflow: refresh Article metadata from Paperpile.json, delete invalid references, "
            "and resolve valid references to Articles by citekey."
        )
    )
    parser.add_argument(
        "--corrections-csv",
        default="corrections/export.csv",
        help="Path to corrections CSV (default: corrections/export.csv).",
    )
    parser.add_argument(
        "--paperpile-json",
        default="Paperpile.json",
        help="Path to Paperpile JSON export (default: Paperpile.json).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for metadata updates (default: 500).",
    )
    parser.add_argument(
        "--skip-paperpile-refresh",
        action="store_true",
        help="Skip Article metadata refresh from Paperpile JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview correction actions without writing to Neo4j.",
    )
    parser.add_argument(
        "--no-paperpile-stubs",
        action="store_true",
        help=(
            "Do not create missing Article stub nodes for correction citekeys. "
            "By default, missing citekeys are backfilled from Paperpile.json."
        ),
    )
    return parser.parse_args()


def _norm_key(value: str) -> str:
    key = (value or "").strip().lower()
    if key in {"", "null", "none", "nan"}:
        return ""
    return key


def _read_field(row: dict[str, str], field_map: dict[str, str], name: str) -> str:
    actual = field_map.get(name, "")
    return (row.get(actual) or "").strip()


def parse_corrections_csv(path: Path) -> ParsedCorrections:
    if not path.exists():
        raise SystemExit(f"Corrections CSV not found: {path}")

    parsed = ParsedCorrections()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise SystemExit(f"CSV has no header row: {path}")

        field_map = {(name or "").strip().lower(): name for name in reader.fieldnames}
        required = {"reference_key", "valid", "citekey"}
        missing = sorted(required - set(field_map))
        if missing:
            raise SystemExit(f"CSV missing required columns {missing}: {path}")

        for idx, row in enumerate(reader, start=2):
            parsed.total_rows += 1
            key = _norm_key(_read_field(row, field_map, "reference_key"))
            valid_flag = _read_field(row, field_map, "valid").upper()
            citekey = _read_field(row, field_map, "citekey")

            if not key:
                parsed.skipped_rows += 1
                continue

            if valid_flag == "F":
                parsed.invalid_keys.add(key)
                if key in parsed.merge_by_key:
                    del parsed.merge_by_key[key]
                continue

            if not citekey:
                parsed.skipped_rows += 1
                continue

            if key in parsed.invalid_keys:
                parsed.skipped_rows += 1
                continue

            existing = parsed.merge_by_key.get(key)
            if existing and existing.lower() != citekey.lower():
                parsed.conflict_rows.append(
                    f"line {idx}: reference_key='{key}' has conflicting citekeys '{existing}' vs '{citekey}'"
                )
                continue
            parsed.merge_by_key[key] = citekey

    return parsed


def _chunked(rows: list[dict], size: int) -> list[list[dict]]:
    size = max(1, int(size))
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def build_article_metadata_updates(session, paperpile_index: dict[str, dict]) -> tuple[list[dict], dict]:
    rows = session.run("MATCH (a:Article) RETURN a.id AS id, a.source_path AS source_path")
    updates: list[dict] = []
    total_articles = 0
    missing_source_path = 0
    no_paperpile_match = 0
    matched = 0

    for row in rows:
        total_articles += 1
        article_id = (row.get("id") or "").strip()
        source_path = (row.get("source_path") or "").strip()
        if not article_id:
            continue
        if not source_path:
            missing_source_path += 1
            continue

        meta = find_metadata_for_pdf(paperpile_index, Path(source_path).name)
        if not meta:
            no_paperpile_match += 1
            continue

        title = (meta.get("title") or "").strip() or None
        update = {
            "id": article_id,
            "title": title,
            "title_norm": normalize_title(title) if title else None,
            "year": meta.get("year"),
            "citekey": (meta.get("citekey") or "").strip() or None,
            "paperpile_id": (meta.get("paperpile_id") or "").strip() or None,
            "doi": (meta.get("doi") or "").strip() or None,
            "journal": (meta.get("journal") or "").strip() or None,
            "publisher": (meta.get("publisher") or "").strip() or None,
        }
        if any(
            update[field] is not None
            for field in ("title", "year", "citekey", "paperpile_id", "doi", "journal", "publisher")
        ):
            updates.append(update)
            matched += 1

    stats = {
        "total_articles": total_articles,
        "missing_source_path": missing_source_path,
        "no_paperpile_match": no_paperpile_match,
        "matched_with_metadata": matched,
    }
    return updates, stats


def _paperpile_year(record: dict) -> int | None:
    published = record.get("published")
    if isinstance(published, dict):
        try:
            return int(str(published.get("year")))
        except Exception:
            pass
    try:
        return int(str(record.get("year")))
    except Exception:
        return None


def _paperpile_citekey_score(meta: dict) -> int:
    keys = ("title", "year", "citekey", "paperpile_id", "doi", "journal", "publisher")
    return sum(1 for k in keys if meta.get(k))


def load_paperpile_by_citekey(path: Path) -> dict[str, dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        return {}

    out: dict[str, dict] = {}
    for record in data:
        if not isinstance(record, dict):
            continue
        citekey = (record.get("citekey") or "").strip()
        if not citekey:
            continue
        meta = {
            "citekey": citekey,
            "title": (record.get("title") or "").strip() or None,
            "year": _paperpile_year(record),
            "paperpile_id": (record.get("_id") or "").strip() or None,
            "doi": (record.get("doi") or "").strip() or None,
            "journal": (record.get("journal") or record.get("journalfull") or "").strip() or None,
            "publisher": (record.get("publisher") or "").strip() or None,
        }
        key = citekey.lower()
        existing = out.get(key)
        if existing is None or _paperpile_citekey_score(meta) > _paperpile_citekey_score(existing):
            out[key] = meta
    return out


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug or "unknown"


def ensure_article_stub_for_citekey(session, citekey: str, meta: dict) -> str:
    paperpile_id = (meta.get("paperpile_id") or "").strip()
    if paperpile_id:
        article_id = f"paperpile::{paperpile_id}"
        source_path = f"paperpile://{paperpile_id}"
    else:
        article_id = f"paperpile-citekey::{_safe_slug(citekey)}"
        source_path = f"paperpile-citekey://{citekey}"

    title = (meta.get("title") or "").strip() or None
    row = session.run(
        """
        MERGE (a:Article {id: $id})
        SET a.citekey = coalesce(a.citekey, $citekey),
            a.paperpile_id = coalesce(a.paperpile_id, $paperpile_id),
            a.title = coalesce($title, a.title),
            a.title_norm = coalesce($title_norm, a.title_norm),
            a.year = coalesce($year, a.year),
            a.doi = coalesce($doi, a.doi),
            a.journal = coalesce($journal, a.journal),
            a.publisher = coalesce($publisher, a.publisher),
            a.source_path = coalesce(a.source_path, $source_path)
        RETURN a.id AS id
        """,
        id=article_id,
        citekey=citekey,
        paperpile_id=paperpile_id or None,
        title=title,
        title_norm=normalize_title(title) if title else None,
        year=meta.get("year"),
        doi=(meta.get("doi") or "").strip() or None,
        journal=(meta.get("journal") or "").strip() or None,
        publisher=(meta.get("publisher") or "").strip() or None,
        source_path=source_path,
    ).single()
    return str((row or {}).get("id") or article_id)


def apply_article_metadata_updates(session, updates: list[dict], batch_size: int) -> int:
    if not updates:
        return 0
    touched = 0
    query = """
    UNWIND $rows AS row
    MATCH (a:Article {id: row.id})
    SET a.title = coalesce(row.title, a.title),
        a.title_norm = coalesce(row.title_norm, a.title_norm),
        a.year = coalesce(row.year, a.year),
        a.citekey = coalesce(row.citekey, a.citekey),
        a.paperpile_id = coalesce(row.paperpile_id, a.paperpile_id),
        a.doi = coalesce(row.doi, a.doi),
        a.journal = coalesce(row.journal, a.journal),
        a.publisher = coalesce(row.publisher, a.publisher)
    RETURN count(a) AS touched
    """
    for chunk in _chunked(updates, batch_size):
        row = session.run(query, rows=chunk).single()
        touched += int((row or {}).get("touched") or 0)
    return touched


def delete_references_by_key(session, key: str) -> tuple[int, int]:
    query = f"""
    MATCH (src:Article)-[:CITES_REFERENCE]->(r:Reference)
    WITH src, r, {REFERENCE_KEY_EXPR} AS ref_key
    WHERE ref_key = $key
    WITH collect(DISTINCT r) AS refs, count(DISTINCT src) AS source_count
    FOREACH (ref IN refs | DETACH DELETE ref)
    RETURN size(refs) AS ref_count, source_count
    """
    row = session.run(query, key=key).single()
    return int((row or {}).get("ref_count") or 0), int((row or {}).get("source_count") or 0)


def lookup_article_by_citekey(session, citekey: str) -> dict | None:
    row = session.run(
        """
        MATCH (a:Article)
        WHERE toLower(coalesce(a.citekey, '')) = toLower($citekey)
        RETURN a.id AS id, a.title AS title, a.citekey AS citekey
        LIMIT 1
        """,
        citekey=citekey,
    ).single()
    return dict(row) if row else None


def merge_references_to_citekey(session, key: str, target_article_id: str) -> tuple[int, int]:
    query = f"""
    MATCH (src:Article)-[:CITES_REFERENCE]->(r:Reference)
    WITH src, r, {REFERENCE_KEY_EXPR} AS ref_key
    WHERE ref_key = $key
    MATCH (dst:Article {{id: $target_article_id}})
    OPTIONAL MATCH (r)-[old:RESOLVES_TO]->(:Article)
    DELETE old
    MERGE (r)-[:RESOLVES_TO]->(dst)
    MERGE (src)-[c:CITES]->(dst)
    SET c.method = $manual_method,
        c.match_score = 1.0
    RETURN count(DISTINCT r) AS refs_updated, count(DISTINCT src) AS source_count
    """
    row = session.run(
        query,
        key=key,
        target_article_id=target_article_id,
        manual_method=MANUAL_CITES_METHOD,
    ).single()
    return int((row or {}).get("refs_updated") or 0), int((row or {}).get("source_count") or 0)


def cleanup_stale_reference_cites(session) -> int:
    row = session.run(
        """
        MATCH (src:Article)-[c:CITES]->(dst:Article)
        WHERE (
            coalesce(c.method, '') STARTS WITH 'reference_'
            OR coalesce(c.method, '') = $manual_method
        )
        AND NOT EXISTS {
            MATCH (src)-[:CITES_REFERENCE]->(:Reference)-[:RESOLVES_TO]->(dst)
        }
        DELETE c
        RETURN count(c) AS removed
        """,
        manual_method=MANUAL_CITES_METHOD,
    ).single()
    return int((row or {}).get("removed") or 0)


def run() -> int:
    args = parse_args()
    corrections_path = Path(args.corrections_csv).expanduser().resolve()
    paperpile_path = Path(args.paperpile_json).expanduser().resolve()
    batch_size = max(1, int(args.batch_size))

    parsed = parse_corrections_csv(corrections_path)
    if parsed.conflict_rows:
        print("Conflicting correction rows detected:")
        for line in parsed.conflict_rows[:30]:
            print(f" - {line}")
        if len(parsed.conflict_rows) > 30:
            print(f" - ... and {len(parsed.conflict_rows) - 30} more")
        raise SystemExit("Resolve conflicting citekey assignments before running cleanup.")

    print(f"Corrections CSV: {corrections_path}")
    print(f"Rows read: {parsed.total_rows}")
    print(f"Rows skipped (blank/no-op): {parsed.skipped_rows}")
    print(f"Invalid reference keys: {len(parsed.invalid_keys)}")
    print(f"Reference->citekey merges: {len(parsed.merge_by_key)}")

    settings = Settings()
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    try:
        with driver.session() as session:
            paperpile_index: dict[str, dict] = {}
            paperpile_by_citekey: dict[str, dict] = {}
            need_paperpile = (not args.skip_paperpile_refresh) or (not args.no_paperpile_stubs)
            if need_paperpile:
                if not paperpile_path.exists():
                    raise SystemExit(f"Paperpile JSON not found: {paperpile_path}")
                paperpile_index = load_paperpile_index(str(paperpile_path))
                paperpile_by_citekey = load_paperpile_by_citekey(paperpile_path)

            if not args.skip_paperpile_refresh:
                updates, refresh_stats = build_article_metadata_updates(session, paperpile_index)
                print("Paperpile refresh scan:")
                print(f" - total articles: {refresh_stats['total_articles']}")
                print(f" - missing source_path: {refresh_stats['missing_source_path']}")
                print(f" - no Paperpile match: {refresh_stats['no_paperpile_match']}")
                print(f" - articles with matched metadata: {refresh_stats['matched_with_metadata']}")
                if args.dry_run:
                    print(f"[dry-run] Would update metadata for {len(updates)} articles.")
                else:
                    touched = apply_article_metadata_updates(session, updates, batch_size=batch_size)
                    print(f"Updated article metadata rows: {touched}")
            else:
                print("Skipping Paperpile metadata refresh (--skip-paperpile-refresh).")

            deleted_refs_total = 0
            deleted_sources_total = 0
            for key in sorted(parsed.invalid_keys):
                if args.dry_run:
                    row = session.run(
                        f"""
                        MATCH (src:Article)-[:CITES_REFERENCE]->(r:Reference)
                        WITH src, r, {REFERENCE_KEY_EXPR} AS ref_key
                        WHERE ref_key = $key
                        RETURN count(DISTINCT r) AS ref_count, count(DISTINCT src) AS source_count
                        """,
                        key=key,
                    ).single()
                    ref_count = int((row or {}).get("ref_count") or 0)
                    source_count = int((row or {}).get("source_count") or 0)
                else:
                    ref_count, source_count = delete_references_by_key(session, key)
                deleted_refs_total += ref_count
                deleted_sources_total += source_count

            print(
                ("[dry-run] " if args.dry_run else "")
                + f"Invalid cleanup matched references: {deleted_refs_total} across {deleted_sources_total} source articles."
            )

            merged_refs_total = 0
            merged_sources_total = 0
            missing_citekeys: list[str] = []
            missing_reference_keys = 0
            stub_articles_created = 0

            for key, citekey in sorted(parsed.merge_by_key.items()):
                target = lookup_article_by_citekey(session, citekey)
                if not target:
                    if not args.no_paperpile_stubs:
                        stub_meta = paperpile_by_citekey.get(citekey.lower())
                        if stub_meta:
                            if args.dry_run:
                                stub_articles_created += 1
                                target = {"id": "__dry_run_stub__"}
                            else:
                                ensure_article_stub_for_citekey(session, citekey, stub_meta)
                                stub_articles_created += 1
                                target = lookup_article_by_citekey(session, citekey)
                    if not target:
                        missing_citekeys.append(citekey)
                        continue

                if args.dry_run:
                    row = session.run(
                        f"""
                        MATCH (src:Article)-[:CITES_REFERENCE]->(r:Reference)
                        WITH src, r, {REFERENCE_KEY_EXPR} AS ref_key
                        WHERE ref_key = $key
                        RETURN count(DISTINCT r) AS refs_updated, count(DISTINCT src) AS source_count
                        """,
                        key=key,
                    ).single()
                    refs_updated = int((row or {}).get("refs_updated") or 0)
                    source_count = int((row or {}).get("source_count") or 0)
                else:
                    refs_updated, source_count = merge_references_to_citekey(session, key, target["id"])

                if refs_updated == 0:
                    missing_reference_keys += 1
                merged_refs_total += refs_updated
                merged_sources_total += source_count

            if args.no_paperpile_stubs:
                print("Paperpile stub creation: disabled (--no-paperpile-stubs).")
            else:
                print(
                    ("[dry-run] " if args.dry_run else "")
                    + f"Paperpile stubs created for missing citekeys: {stub_articles_created}"
                )
            print(
                ("[dry-run] " if args.dry_run else "")
                + f"Merge cleanup resolved references: {merged_refs_total} across {merged_sources_total} source articles."
            )
            print(f"Reference keys with no matching references: {missing_reference_keys}")
            if missing_citekeys:
                uniq = sorted({c for c in missing_citekeys})
                print(f"Citekeys not found in Article nodes: {len(uniq)}")
                for ck in uniq[:30]:
                    print(f" - {ck}")
                if len(uniq) > 30:
                    print(f" - ... and {len(uniq) - 30} more")

            if args.dry_run:
                row = session.run(
                    """
                    MATCH (src:Article)-[c:CITES]->(dst:Article)
                    WHERE (
                        coalesce(c.method, '') STARTS WITH 'reference_'
                        OR coalesce(c.method, '') = $manual_method
                    )
                    AND NOT EXISTS {
                        MATCH (src)-[:CITES_REFERENCE]->(:Reference)-[:RESOLVES_TO]->(dst)
                    }
                    RETURN count(c) AS stale_edges
                    """,
                    manual_method=MANUAL_CITES_METHOD,
                ).single()
                stale = int((row or {}).get("stale_edges") or 0)
                print(f"[dry-run] Stale CITES edges that would be removed: {stale}")
            else:
                removed_stale = cleanup_stale_reference_cites(session)
                print(f"Removed stale CITES edges: {removed_stale}")

    finally:
        driver.close()

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
