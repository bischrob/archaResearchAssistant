from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
from pathlib import Path
import re
from typing import Iterable

import numpy as np
from neo4j import GraphDatabase

from .metadata_provider import metadata_title_year_key
from .pdf_processing import ArticleDoc


def _normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    normalized = doi.strip().lower()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized)
    return normalized.strip().rstrip(".;,")


def _author_token_set(names: list[str]) -> set[str]:
    out: set[str] = set()
    for name in names:
        for tok in re.findall(r"[a-z][a-z'-]+", (name or "").lower()):
            if len(tok) >= 3:
                out.add(tok)
    return out


class HashingEmbedder:
    def __init__(self, dimension: int = 384) -> None:
        self.dimension = dimension
        self._token_re = re.compile(r"[a-z0-9]+")

    def _encode_one(self, text: str) -> list[float]:
        vec = np.zeros(self.dimension, dtype=np.float32)
        for token in self._token_re.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if (digest[4] % 2 == 0) else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._encode_one(t) for t in texts]


class GraphStore:
    def __init__(self, uri: str, user: str, password: str, embedding_model: str | None = None) -> None:
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.embedder = HashingEmbedder(dimension=384)

    @property
    def embedding_dimension(self) -> int:
        return self.embedder.dimension

    def close(self) -> None:
        self.driver.close()

    def setup_schema(self, vector_dimensions: int) -> None:
        statements = [
            "CREATE CONSTRAINT article_id IF NOT EXISTS FOR (a:Article) REQUIRE a.id IS UNIQUE",
            "CREATE CONSTRAINT author_norm IF NOT EXISTS FOR (p:Author) REQUIRE p.name_norm IS UNIQUE",
            "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT token_value IF NOT EXISTS FOR (t:Token) REQUIRE t.value IS UNIQUE",
            "CREATE CONSTRAINT reference_id IF NOT EXISTS FOR (r:Reference) REQUIRE r.id IS UNIQUE",
            (
                "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS "
                "FOR (c:Chunk) ON (c.embedding) "
                "OPTIONS {indexConfig: {`vector.dimensions`: $dims, `vector.similarity_function`: 'cosine'}}"
            ),
            "CREATE FULLTEXT INDEX chunk_text IF NOT EXISTS FOR (c:Chunk) ON EACH [c.text]",
            "CREATE FULLTEXT INDEX author_search IF NOT EXISTS FOR (p:Author) ON EACH [p.name, p.name_norm]",
            "CREATE FULLTEXT INDEX article_search IF NOT EXISTS FOR (a:Article) ON EACH [a.title, a.title_norm, a.citekey, a.doi]",
            "CREATE TEXT INDEX author_name_norm_text IF NOT EXISTS FOR (p:Author) ON (p.name_norm)",
            "CREATE TEXT INDEX article_title_norm_text IF NOT EXISTS FOR (a:Article) ON (a.title_norm)",
            "CREATE TEXT INDEX article_citekey_text IF NOT EXISTS FOR (a:Article) ON (a.citekey)",
            "CREATE TEXT INDEX article_doi_text IF NOT EXISTS FOR (a:Article) ON (a.doi)",
            "CREATE TEXT INDEX article_zotero_persistent_id_text IF NOT EXISTS FOR (a:Article) ON (a.zotero_persistent_id)",
            "CREATE TEXT INDEX article_zotero_item_key_text IF NOT EXISTS FOR (a:Article) ON (a.zotero_item_key)",
            "CREATE TEXT INDEX article_zotero_attachment_key_text IF NOT EXISTS FOR (a:Article) ON (a.zotero_attachment_key)",
            "CREATE TEXT INDEX article_title_year_key_text IF NOT EXISTS FOR (a:Article) ON (a.title_year_key)",
            "CREATE TEXT INDEX article_metadata_source_text IF NOT EXISTS FOR (a:Article) ON (a.metadata_source)",
            "CREATE INDEX article_year IF NOT EXISTS FOR (a:Article) ON (a.year)",
            "CREATE TEXT INDEX reference_title_norm_text IF NOT EXISTS FOR (r:Reference) ON (r.title_norm)",
            "CREATE TEXT INDEX reference_doi_text IF NOT EXISTS FOR (r:Reference) ON (r.doi)",
            "CREATE TEXT INDEX reference_source_text IF NOT EXISTS FOR (r:Reference) ON (r.source)",
        ]
        with self.driver.session() as session:
            for stmt in statements:
                session.run(stmt, dims=vector_dimensions)

    def ingest_articles(
        self,
        articles: list[ArticleDoc],
        should_cancel=None,
        article_progress_callback=None,
    ) -> None:
        chunk_texts = [chunk.text for article in articles for chunk in article.chunks]
        embeddings = self.embedder.encode(chunk_texts) if chunk_texts else []

        emb_iter = iter(embeddings)
        with self.driver.session() as session:
            for article_idx, article in enumerate(articles, start=1):
                if should_cancel and should_cancel():
                    raise RuntimeError("Ingest cancelled by user.")
                article_embeddings = [next(emb_iter) for _ in article.chunks]
                session.execute_write(self._ingest_article_tx, article, article_embeddings, should_cancel)
                if article_progress_callback:
                    article_progress_callback(article_idx, len(articles), f"Uploaded {article.article_id}")

        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")
        self._link_article_citations(articles)

    @staticmethod
    def _ingest_article_tx(tx, article: ArticleDoc, article_embeddings: list[list[float]], should_cancel=None) -> None:
        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")
        tx.run(
            """
            MERGE (a:Article {id: $id})
            SET a.title = $title,
                a.title_norm = $title_norm,
                a.year = $year,
                a.source_path = $source_path,
                a.citekey = $citekey,
                a.paperpile_id = $paperpile_id,
                a.zotero_persistent_id = $zotero_persistent_id,
                a.zotero_item_key = $zotero_item_key,
                a.zotero_attachment_key = $zotero_attachment_key,
                a.doi = $doi,
                a.journal = $journal,
                a.publisher = $publisher,
                a.title_year_key = $title_year_key,
                a.metadata_source = $metadata_source
            """,
            id=article.article_id,
            title=article.title,
            title_norm=article.normalized_title,
            year=article.year,
            source_path=article.source_path,
            citekey=article.citekey,
            paperpile_id=article.paperpile_id,
            zotero_persistent_id=article.zotero_persistent_id,
            zotero_item_key=article.zotero_item_key,
            zotero_attachment_key=article.zotero_attachment_key,
            doi=article.doi,
            journal=article.journal,
            publisher=article.publisher,
            title_year_key=article.title_year_key,
            metadata_source=article.metadata_source,
        )

        # Refresh chunk and authorship relationships for this article in one tx.
        tx.run(
            """
            MATCH (a:Article {id: $article_id})
            OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
            DETACH DELETE c
            """,
            article_id=article.article_id,
        )
        tx.run(
            """
            MATCH (a:Article {id: $article_id})
            OPTIONAL MATCH (:Author)-[w:WROTE]->(a)
            DELETE w
            """,
            article_id=article.article_id,
        )

        for pos, author_name in enumerate(article.authors):
            author_name = (author_name or "").strip()
            if not author_name:
                continue
            tx.run(
                """
                MERGE (p:Author {name_norm: $author_norm})
                SET p.name = $author_name
                WITH p
                MATCH (a:Article {id: $article_id})
                MERGE (p)-[w:WROTE]->(a)
                SET w.position = $position
                """,
                author_norm=author_name.lower(),
                author_name=author_name,
                article_id=article.article_id,
                position=pos,
            )

        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")

        for chunk, emb in zip(article.chunks, article_embeddings):
            tx.run(
                """
                MERGE (c:Chunk {id: $id})
                SET c.text = $text,
                    c.index = $index,
                    c.page_start = $page_start,
                    c.page_end = $page_end,
                    c.tokens = $tokens,
                    c.embedding = $embedding
                WITH c
                MATCH (a:Article {id: $article_id})
                MERGE (c)-[:IN_ARTICLE]->(a)
                """,
                id=chunk.chunk_id,
                text=chunk.text,
                index=chunk.index,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                tokens=chunk.tokens,
                embedding=emb,
                article_id=article.article_id,
            )

            token_rows = [{"value": token, "count": count} for token, count in chunk.token_counts.items()]
            if token_rows:
                tx.run(
                    """
                    UNWIND $rows AS row
                    MERGE (t:Token {value: row.value})
                    WITH t, row
                    MATCH (c:Chunk {id: $chunk_id})
                    MERGE (c)-[m:MENTIONS]->(t)
                    SET m.count = row.count
                    """,
                    rows=token_rows,
                    chunk_id=chunk.chunk_id,
                )

        # Refresh reference-related graph edges for this source article to
        # avoid stale/duplicate references during full re-ingest runs.
        tx.run(
            """
            MATCH (a:Article {id: $article_id})
            OPTIONAL MATCH (a)-[out:CITES]->(:Article)
            DELETE out
            WITH a
            OPTIONAL MATCH (a)-[:CITES_REFERENCE]->(r:Reference)
            WHERE r.id STARTS WITH $ref_prefix
            DETACH DELETE r
            """,
            article_id=article.article_id,
            ref_prefix=f"{article.article_id}::ref::",
        )

        if should_cancel and should_cancel():
            raise RuntimeError("Ingest cancelled by user.")

        for citation in article.citations:
            tx.run(
                """
                MERGE (r:Reference {id: $id})
                SET r.raw_text = $raw_text,
                    r.year = $year,
                    r.title_guess = $title_guess,
                    r.title_norm = $title_norm,
                    r.author_tokens = $author_tokens,
                    r.doi = $doi,
                    r.source = $source,
                    r.type_guess = $type_guess,
                    r.quality_score = $quality_score
                WITH r
                MATCH (a:Article {id: $article_id})
                MERGE (a)-[:CITES_REFERENCE]->(r)
                """,
                id=citation.citation_id,
                raw_text=citation.raw_text,
                year=citation.year,
                title_guess=citation.title_guess,
                title_norm=citation.normalized_title,
                author_tokens=citation.author_tokens or [],
                doi=citation.doi,
                source=citation.source,
                type_guess=citation.type_guess,
                quality_score=citation.quality_score,
                article_id=article.article_id,
            )

    def _link_article_citations(self, articles: Iterable[ArticleDoc]) -> None:
        by_title = {a.article_id: a for a in articles}
        target_profiles = {
            article_id: {
                "doi": _normalize_doi(article.doi),
                "author_tokens": _author_token_set(article.authors or ([article.author] if article.author else [])),
                "year": article.year,
                "title_norm": article.normalized_title or "",
            }
            for article_id, article in by_title.items()
        }
        links: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        for source in articles:
            for citation in source.citations:
                if not citation.normalized_title:
                    continue
                best_target = None
                best_score = 0.0
                best_title_score = 0.0
                best_author_overlap = 0.0
                best_year_match = False
                best_method = "reference_title_match"
                citation_doi = _normalize_doi(citation.doi)
                citation_author_tokens = set(citation.author_tokens or [])
                for target in by_title.values():
                    if target.article_id == source.article_id:
                        continue
                    profile = target_profiles[target.article_id]

                    if citation_doi and profile["doi"] and citation_doi == profile["doi"]:
                        best_target = target.article_id
                        best_score = 1.0
                        best_title_score = 1.0
                        best_author_overlap = 1.0
                        best_year_match = True
                        best_method = "reference_doi_match"
                        break

                    title_score = SequenceMatcher(None, citation.normalized_title, profile["title_norm"]).ratio()
                    year_match = (
                        citation.year is None
                        or profile["year"] is None
                        or abs(citation.year - profile["year"]) <= 1
                    )
                    if citation.year is not None and profile["year"] is not None and not year_match and title_score < 0.88:
                        continue

                    author_overlap = 0.0
                    if citation_author_tokens and profile["author_tokens"]:
                        author_overlap = len(citation_author_tokens & profile["author_tokens"]) / max(
                            1, len(citation_author_tokens)
                        )

                    score = (0.80 * title_score) + (0.15 * author_overlap) + (0.05 if year_match else 0.0)
                    if score > best_score:
                        best_score = score
                        best_target = target.article_id
                        best_title_score = title_score
                        best_author_overlap = author_overlap
                        best_year_match = year_match
                        best_method = "reference_structured_match" if author_overlap > 0 else "reference_title_match"

                accepted = False
                if best_target:
                    if best_method == "reference_doi_match":
                        accepted = True
                    elif best_score >= 0.62 and best_title_score >= 0.55 and best_year_match:
                        accepted = True
                    elif best_title_score >= 0.80:
                        accepted = True

                if accepted and best_target:
                    pair = (source.article_id, best_target)
                    seen_pairs.add(pair)
                    links.append(
                        {
                            "source": source.article_id,
                            "target": best_target,
                            "reference_id": citation.citation_id,
                            "score": round(min(1.0, best_score), 4),
                            "method": best_method,
                        }
                    )

        # Fallback: infer citation links from in-text author/year mentions.
        for source in articles:
            source_text = " ".join(chunk.text.lower() for chunk in source.chunks)
            for target in articles:
                if source.article_id == target.article_id:
                    continue
                if target.year is None:
                    continue
                pair = (source.article_id, target.article_id)
                if pair in seen_pairs:
                    continue
                target_author_norm = (target.author or "").strip().lower()
                if not target_author_norm:
                    continue
                author_hit = target_author_norm in source_text
                year_hit = str(target.year) in source_text
                if author_hit and year_hit:
                    seen_pairs.add(pair)
                    links.append(
                        {
                            "source": source.article_id,
                            "target": target.article_id,
                            "reference_id": None,
                            "score": 0.55,
                            "method": "in_text_author_year",
                        }
                    )

        # If still disconnected in small test sets, connect same-author prior works by year.
        for source in articles:
            if source.year is None:
                continue
            source_author_norm = (source.author or "").strip().lower()
            if not source_author_norm:
                continue
            for target in articles:
                if target.year is None:
                    continue
                if source.article_id == target.article_id:
                    continue
                target_author_norm = (target.author or "").strip().lower()
                if not target_author_norm:
                    continue
                if source_author_norm != target_author_norm:
                    continue
                if source.year <= target.year:
                    continue
                pair = (source.article_id, target.article_id)
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                links.append(
                    {
                        "source": source.article_id,
                        "target": target.article_id,
                        "reference_id": None,
                        "score": 0.35,
                        "method": "same_author_prior_work",
                    }
                )

        if not links:
            return
        with self.driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MATCH (src:Article {id: row.source})
                MATCH (dst:Article {id: row.target})
                MERGE (src)-[c:CITES]->(dst)
                SET c.match_score = row.score,
                    c.method = row.method
                WITH src, dst, row
                OPTIONAL MATCH (src)-[:CITES_REFERENCE]->(r:Reference {id: row.reference_id})
                FOREACH (_ IN CASE WHEN r IS NULL THEN [] ELSE [1] END |
                    MERGE (r)-[:RESOLVES_TO]->(dst)
                )
                """,
                rows=links,
            )

    def token_query(self, query_tokens: list[str], limit: int) -> list[dict]:
        if not query_tokens:
            return []
        with self.driver.session() as session:
            result = session.run(
                """
                MATCH (t:Token)<-[m:MENTIONS]-(c:Chunk)-[:IN_ARTICLE]->(a:Article)
                WHERE t.value IN $tokens
                WITH c, a, sum(m.count) AS token_score
                ORDER BY token_score DESC
                LIMIT $limit
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                    RETURN [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out
                }
                CALL (a) {
                    OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                    RETURN [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                }
                RETURN c.id AS chunk_id,
                       c.text AS chunk_text,
                       c.index AS chunk_index,
                       c.page_start AS page_start,
                       c.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..8] AS authors,
                       token_score,
                       cites_out,
                       cited_by
                ORDER BY token_score DESC
                """,
                tokens=query_tokens,
                limit=limit,
            )
            return [dict(r) for r in result]

    def vector_query(self, query_text: str, limit: int) -> list[dict]:
        vector = self.embedder.encode([query_text])[0]
        with self.driver.session() as session:
            result = session.run(
                """
                CALL db.index.vector.queryNodes('chunk_embedding', $k, $embedding)
                YIELD node, score
                MATCH (node)-[:IN_ARTICLE]->(a:Article)
                WITH node, a, score
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                    RETURN [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out
                }
                CALL (a) {
                    OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                    RETURN [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                }
                RETURN node.id AS chunk_id,
                       node.text AS chunk_text,
                       node.index AS chunk_index,
                       node.page_start AS page_start,
                       node.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..8] AS authors,
                       score AS vector_score,
                       cites_out,
                       cited_by
                ORDER BY vector_score DESC
                LIMIT $k
                """,
                k=limit,
                embedding=vector,
            )
            return [dict(r) for r in result]

    def author_query(self, query_terms: list[str], limit: int) -> list[dict]:
        terms = list(dict.fromkeys(t.strip().lower() for t in query_terms if t and t.strip()))
        if not terms:
            return []
        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $terms AS term
                CALL db.index.fulltext.queryNodes('author_search', term)
                YIELD node, score
                WITH node AS auth, sum(score) AS author_match_score
                MATCH (auth)-[:WROTE]->(a:Article)<-[:IN_ARTICLE]-(c:Chunk)
                WITH c, a, toFloat(sum(author_match_score)) AS author_score
                ORDER BY author_score DESC, a.year DESC
                LIMIT $limit
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                    RETURN [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out
                }
                CALL (a) {
                    OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                    RETURN [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                }
                RETURN c.id AS chunk_id,
                       c.text AS chunk_text,
                       c.index AS chunk_index,
                       c.page_start AS page_start,
                       c.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..8] AS authors,
                       author_score,
                       cites_out,
                       cited_by
                ORDER BY author_score DESC, article_year DESC
                """,
                terms=terms,
                limit=limit,
            )
            return [dict(r) for r in result]

    def title_query(self, query_terms: list[str], limit: int) -> list[dict]:
        terms = list(dict.fromkeys(t.strip().lower() for t in query_terms if t and t.strip()))
        if not terms:
            return []
        with self.driver.session() as session:
            result = session.run(
                """
                UNWIND $terms AS term
                CALL db.index.fulltext.queryNodes('article_search', term)
                YIELD node, score
                WITH node AS a, sum(score) AS article_score
                MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                WITH c, a, toFloat(article_score) AS title_score
                ORDER BY title_score DESC, a.year DESC
                LIMIT $limit
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                    RETURN [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out
                }
                CALL (a) {
                    OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                    RETURN [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                }
                RETURN c.id AS chunk_id,
                       c.text AS chunk_text,
                       c.index AS chunk_index,
                       c.page_start AS page_start,
                       c.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..8] AS authors,
                       toFloat(title_score) AS title_score,
                       cites_out,
                       cited_by
                ORDER BY title_score DESC, article_year DESC
                """,
                terms=terms,
                limit=limit,
            )
            return [dict(r) for r in result]

    def graph_stats(self) -> dict:
        query = """
        MATCH (a:Article) WITH count(a) AS articles
        MATCH (c:Chunk) WITH articles, count(c) AS chunks
        MATCH (t:Token) WITH articles, chunks, count(t) AS tokens
        MATCH (r:Reference) WITH articles, chunks, tokens, count(r) AS references
        OPTIONAL MATCH (:Article)-[x:CITES]->(:Article)
        RETURN articles, chunks, tokens, references, count(x) AS cites
        """
        with self.driver.session() as session:
            row = session.run(query).single()
            if not row:
                return {"articles": 0, "chunks": 0, "tokens": 0, "references": 0, "cites": 0}
            return dict(row)

    def existing_article_ids(self) -> set[str]:
        with self.driver.session() as session:
            rows = session.run("MATCH (a:Article) RETURN a.id AS id")
            return {r["id"] for r in rows if r.get("id")}

    def existing_article_identity_sets(self) -> dict[str, set[str]]:
        with self.driver.session() as session:
            rows = session.run(
                """
                MATCH (a:Article)
                RETURN a.id AS id,
                       a.title AS title,
                       a.year AS year,
                       a.doi AS doi,
                       a.zotero_persistent_id AS zotero_persistent_id,
                       a.zotero_item_key AS zotero_item_key,
                       a.zotero_attachment_key AS zotero_attachment_key,
                       a.title_year_key AS title_year_key,
                       a.source_path AS source_path
                """
            )
            out = {
                "article_ids": set(),
                "doi": set(),
                "zotero_persistent_id": set(),
                "zotero_item_key": set(),
                "zotero_attachment_key": set(),
                "title_year_key": set(),
                "title_year_key_normalized": set(),
                "file_stem": set(),
            }
            for row in rows:
                article_id = (row.get("id") or "").strip()
                if article_id:
                    out["article_ids"].add(article_id)
                    out["file_stem"].add(article_id.lower())

                doi = _normalize_doi(row.get("doi"))
                if doi:
                    out["doi"].add(doi)

                persistent_id = (row.get("zotero_persistent_id") or "").strip()
                if persistent_id:
                    out["zotero_persistent_id"].add(persistent_id)

                item_key = (row.get("zotero_item_key") or "").strip()
                if item_key:
                    out["zotero_item_key"].add(item_key.lower())

                attachment_key = (row.get("zotero_attachment_key") or "").strip()
                if attachment_key:
                    out["zotero_attachment_key"].add(attachment_key.lower())

                title_year_key = (row.get("title_year_key") or "").strip()
                if title_year_key:
                    out["title_year_key"].add(title_year_key.lower())
                normalized_title_year_key = metadata_title_year_key(
                    {
                        "title": row.get("title"),
                        "year": row.get("year"),
                    }
                )
                if normalized_title_year_key:
                    out["title_year_key_normalized"].add(normalized_title_year_key.lower())

                source_path = (row.get("source_path") or "").strip()
                if source_path:
                    stem = Path(source_path).stem.strip().lower()
                    if stem:
                        out["file_stem"].add(stem)
            return out

    def existing_identity_hits(
        self,
        *,
        dois: set[str],
        zotero_persistent_ids: set[str],
        zotero_item_keys: set[str],
        zotero_attachment_keys: set[str],
        title_year_keys: set[str],
        file_stems: set[str],
    ) -> dict[str, set[str]]:
        """
        Return only identity values that already exist in Neo4j for the provided candidate sets.
        This is much cheaper than scanning all Article identities for large graphs.
        """
        hits = {
            "doi": set(),
            "zotero_persistent_id": set(),
            "zotero_item_key": set(),
            "zotero_attachment_key": set(),
            "title_year_key": set(),
            "title_year_key_normalized": set(),
            "file_stem": set(),
        }
        with self.driver.session() as session:
            if dois:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE toLower(coalesce(a.doi, '')) IN $values
                    RETURN toLower(a.doi) AS value
                    """,
                    values=sorted(dois),
                )
                hits["doi"] = {str(r.get("value") or "").strip() for r in rows if r.get("value")}

            if zotero_persistent_ids:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE coalesce(a.zotero_persistent_id, '') IN $values
                    RETURN a.zotero_persistent_id AS value
                    """,
                    values=sorted(zotero_persistent_ids),
                )
                hits["zotero_persistent_id"] = {str(r.get("value") or "").strip() for r in rows if r.get("value")}

            if zotero_item_keys:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE toLower(coalesce(a.zotero_item_key, '')) IN $values
                    RETURN toLower(a.zotero_item_key) AS value
                    """,
                    values=sorted(zotero_item_keys),
                )
                hits["zotero_item_key"] = {str(r.get("value") or "").strip() for r in rows if r.get("value")}

            if zotero_attachment_keys:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE toLower(coalesce(a.zotero_attachment_key, '')) IN $values
                    RETURN toLower(a.zotero_attachment_key) AS value
                    """,
                    values=sorted(zotero_attachment_keys),
                )
                hits["zotero_attachment_key"] = {str(r.get("value") or "").strip() for r in rows if r.get("value")}

            if title_year_keys:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE toLower(coalesce(a.title_year_key, '')) IN $values
                    RETURN toLower(a.title_year_key) AS value
                    """,
                    values=sorted(title_year_keys),
                )
                title_hits = {str(r.get("value") or "").strip() for r in rows if r.get("value")}
                hits["title_year_key"] = title_hits
                hits["title_year_key_normalized"] = set(title_hits)

            if file_stems:
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WHERE toLower(coalesce(a.id, '')) IN $values
                    RETURN toLower(a.id) AS value
                    """,
                    values=sorted(file_stems),
                )
                stem_hits = {str(r.get("value") or "").strip() for r in rows if r.get("value")}
                rows = session.run(
                    """
                    MATCH (a:Article)
                    WITH toLower(replace(coalesce(a.source_path, ''), '\\\\', '/')) AS source_path
                    WITH split(source_path, '/')[-1] AS filename
                    WITH CASE
                         WHEN filename ENDS WITH '.pdf' THEN substring(filename, 0, size(filename) - 4)
                         ELSE filename
                         END AS stem
                    WHERE stem IN $values
                    RETURN stem AS value
                    """,
                    values=sorted(file_stems),
                )
                stem_hits.update(str(r.get("value") or "").strip() for r in rows if r.get("value"))
                hits["file_stem"] = stem_hits
        return hits

    def reconcile_zotero_persistent_ids(self, rows: list[dict]) -> dict[str, object]:
        """
        Link missing Zotero persistent IDs onto already-ingested articles using exact-match identities.
        This avoids expensive re-ingest work for articles that are already present in Neo4j.
        """
        matched = 0
        unresolved = 0
        ambiguous = 0
        examples: list[dict[str, str]] = []

        item_keys = {
            str(row.get("zotero_item_key") or "").strip().lower()
            for row in rows
            if str(row.get("zotero_item_key") or "").strip()
        }
        attachment_keys = {
            str(row.get("zotero_attachment_key") or "").strip().lower()
            for row in rows
            if str(row.get("zotero_attachment_key") or "").strip()
        }
        dois = {
            _normalize_doi(row.get("doi"))
            for row in rows
            if _normalize_doi(row.get("doi"))
        }
        title_year_keys = {
            (metadata_title_year_key(row) or "").strip().lower()
            for row in rows
            if (metadata_title_year_key(row) or "").strip()
        }

        def _unique_match_map(session, query: str, values: set[str]) -> tuple[dict[str, str], set[str]]:
            if not values:
                return {}, set()
            rows_out = session.run(query, values=sorted(values))
            unique: dict[str, str] = {}
            ambiguous_values: set[str] = set()
            for rec in rows_out:
                value = str(rec.get("value") or "").strip()
                ids = [str(x).strip() for x in (rec.get("ids") or []) if str(x).strip()]
                if not value or not ids:
                    continue
                if len(ids) == 1:
                    unique[value] = ids[0]
                else:
                    ambiguous_values.add(value)
            return unique, ambiguous_values

        with self.driver.session() as session:
            item_map, item_ambiguous = _unique_match_map(
                session,
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.zotero_item_key, '')) IN $values
                WITH toLower(a.zotero_item_key) AS value, collect(DISTINCT a.id) AS ids
                RETURN value, ids
                """,
                item_keys,
            )
            attachment_map, attachment_ambiguous = _unique_match_map(
                session,
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.zotero_attachment_key, '')) IN $values
                WITH toLower(a.zotero_attachment_key) AS value, collect(DISTINCT a.id) AS ids
                RETURN value, ids
                """,
                attachment_keys,
            )
            doi_map, doi_ambiguous = _unique_match_map(
                session,
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.doi, '')) IN $values
                WITH toLower(a.doi) AS value, collect(DISTINCT a.id) AS ids
                RETURN value, ids
                """,
                dois,
            )
            title_year_map, title_year_ambiguous = _unique_match_map(
                session,
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.title_year_key, '')) IN $values
                WITH toLower(a.title_year_key) AS value, collect(DISTINCT a.id) AS ids
                RETURN value, ids
                """,
                title_year_keys,
            )

            updates: list[dict[str, str]] = []
            for row in rows:
                persistent_id = str(row.get("zotero_persistent_id") or "").strip()
                if not persistent_id:
                    unresolved += 1
                    continue

                item_key = str(row.get("zotero_item_key") or "").strip().lower()
                attachment_key = str(row.get("zotero_attachment_key") or "").strip().lower()
                doi = _normalize_doi(row.get("doi"))
                title_year_key = (metadata_title_year_key(row) or "").strip().lower()

                match_id = ""
                match_method = ""
                ambiguous_hit = False

                if item_key:
                    if item_key in item_ambiguous:
                        ambiguous_hit = True
                    elif item_key in item_map:
                        match_id = item_map[item_key]
                        match_method = "zotero_item_key"
                if not match_id and not ambiguous_hit and attachment_key:
                    if attachment_key in attachment_ambiguous:
                        ambiguous_hit = True
                    elif attachment_key in attachment_map:
                        match_id = attachment_map[attachment_key]
                        match_method = "zotero_attachment_key"
                if not match_id and not ambiguous_hit and doi:
                    if doi in doi_ambiguous:
                        ambiguous_hit = True
                    elif doi in doi_map:
                        match_id = doi_map[doi]
                        match_method = "doi"
                if not match_id and not ambiguous_hit and title_year_key:
                    if title_year_key in title_year_ambiguous:
                        ambiguous_hit = True
                    elif title_year_key in title_year_map:
                        match_id = title_year_map[title_year_key]
                        match_method = "title_year_key"

                if not match_id:
                    if ambiguous_hit:
                        ambiguous += 1
                    else:
                        unresolved += 1
                    continue

                updates.append(
                    {
                        "id": match_id,
                        "zotero_persistent_id": persistent_id,
                        "zotero_item_key": item_key,
                        "zotero_attachment_key": attachment_key,
                    }
                )
                matched += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "article_id": match_id,
                            "zotero_persistent_id": persistent_id,
                            "method": match_method,
                            "title": str(row.get("title") or ""),
                        }
                    )

            if updates:
                session.run(
                    """
                    UNWIND $rows AS row
                    MATCH (a:Article {id: row.id})
                    SET a.zotero_persistent_id = row.zotero_persistent_id,
                        a.zotero_item_key = CASE
                            WHEN row.zotero_item_key = '' THEN a.zotero_item_key
                            ELSE row.zotero_item_key
                        END,
                        a.zotero_attachment_key = CASE
                            WHEN row.zotero_attachment_key = '' THEN a.zotero_attachment_key
                            ELSE row.zotero_attachment_key
                        END,
                        a.metadata_source = CASE
                            WHEN coalesce(a.metadata_source, '') = '' THEN 'zotero'
                            ELSE a.metadata_source
                        END
                    """,
                    rows=updates,
                )

        return {
            "matched": matched,
            "unresolved": unresolved,
            "ambiguous": ambiguous,
            "examples": examples,
        }

    def article_by_citekey(self, citekey: str, chunk_limit: int = 3) -> dict | None:
        key = (citekey or "").strip()
        if not key:
            return None
        with self.driver.session() as session:
            row = session.run(
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.citekey, '')) = toLower($citekey)
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                    RETURN count(c) AS chunk_count
                }
                CALL (a) {
                    OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                    WITH c
                    ORDER BY coalesce(c.index, 0) ASC
                    LIMIT $chunk_limit
                    RETURN collect(
                        {
                            id: c.id,
                            index: c.index,
                            page_start: c.page_start,
                            page_end: c.page_end,
                            text: substring(coalesce(c.text, ''), 0, 1200)
                        }
                    ) AS sample_chunks
                }
                CALL (a) {
                    OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                    RETURN [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..10] AS cites_out
                }
                CALL (a) {
                    OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                    RETURN [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..10] AS cited_by
                }
                RETURN a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       a.journal AS article_journal,
                       a.publisher AS article_publisher,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..15] AS authors,
                       chunk_count,
                       sample_chunks,
                       cites_out,
                       cited_by
                LIMIT 1
                """,
                citekey=key,
                chunk_limit=max(1, int(chunk_limit)),
            ).single()
            return dict(row) if row else None

    def article_chunks_by_citekey(self, citekey: str) -> dict | None:
        key = (citekey or "").strip()
        if not key:
            return None
        with self.driver.session() as session:
            row = session.run(
                """
                MATCH (a:Article)
                WHERE toLower(coalesce(a.citekey, '')) = toLower($citekey)
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                    WITH c
                    ORDER BY coalesce(c.index, 0) ASC
                    RETURN collect(
                        {
                            id: c.id,
                            index: c.index,
                            page_start: c.page_start,
                            page_end: c.page_end,
                            text: coalesce(c.text, '')
                        }
                    ) AS chunks
                }
                RETURN a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       a.journal AS article_journal,
                       a.publisher AS article_publisher,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..15] AS authors,
                       chunks
                LIMIT 1
                """,
                citekey=key,
            ).single()
            return dict(row) if row else None

    def article_chunks_by_id(self, article_id: str) -> dict | None:
        key = (article_id or "").strip()
        if not key:
            return None
        with self.driver.session() as session:
            row = session.run(
                """
                MATCH (a:Article {id: $article_id})
                CALL (a) {
                    MATCH (auth:Author)-[w:WROTE]->(a)
                    WITH auth, w ORDER BY w.position ASC
                    RETURN collect(auth.name) AS authors
                }
                CALL (a) {
                    OPTIONAL MATCH (a)<-[:IN_ARTICLE]-(c:Chunk)
                    WITH c
                    ORDER BY coalesce(c.index, 0) ASC
                    RETURN collect(
                        {
                            id: c.id,
                            index: c.index,
                            page_start: c.page_start,
                            page_end: c.page_end,
                            text: coalesce(c.text, '')
                        }
                    ) AS chunks
                }
                RETURN a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       a.citekey AS article_citekey,
                       a.doi AS article_doi,
                       a.source_path AS article_source_path,
                       a.journal AS article_journal,
                       a.publisher AS article_publisher,
                       coalesce(head(authors), 'Unknown Author') AS author,
                       authors[0..15] AS authors,
                       chunks
                LIMIT 1
                """,
                article_id=key,
            ).single()
            return dict(row) if row else None

    def articles_by_citekeys(self, citekeys: list[str], chunk_limit: int = 3) -> list[dict]:
        out: list[dict] = []
        seen: set[str] = set()
        for raw_key in citekeys:
            key = (raw_key or "").strip()
            if not key:
                continue
            normalized = key.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            row = self.article_by_citekey(key, chunk_limit=chunk_limit)
            if row:
                out.append(row)
        return out
