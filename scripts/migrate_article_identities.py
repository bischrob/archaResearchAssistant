#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.rag.config import Settings
from src.rag.neo4j_store import GraphStore

TITLE_WORD_RE = re.compile(r"[a-z0-9]+")


def _title_year_key(title: str | None, year: int | None) -> str | None:
    if not title or year is None:
        return None
    words = " ".join(TITLE_WORD_RE.findall(title.lower())).strip()
    if not words:
        return None
    return f"{words}|{int(year)}"


def main() -> None:
    settings = Settings()
    store = GraphStore(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.embedding_model)
    try:
        with store.driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Article)
                RETURN a.id AS id,
                       a.title AS title,
                       a.year AS year,
                       a.source_path AS source_path,
                       a.metadata_source AS metadata_source
                """
            )
            updated = 0
            for row in rows:
                article_id = row.get("id")
                if not article_id:
                    continue
                title_year_key = _title_year_key(row.get("title"), row.get("year"))
                source = (row.get("metadata_source") or "").strip() or "paperpile"
                session.run(
                    """
                    MATCH (a:Article {id: $id})
                    SET a.title_year_key = coalesce(a.title_year_key, $title_year_key),
                        a.metadata_source = coalesce(a.metadata_source, $metadata_source)
                    """,
                    id=article_id,
                    title_year_key=title_year_key,
                    metadata_source=source,
                )
                updated += 1

        print(f"Updated identity fields for {updated} articles.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
