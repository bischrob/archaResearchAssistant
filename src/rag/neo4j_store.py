from __future__ import annotations

from difflib import SequenceMatcher
import hashlib
import re
from typing import Iterable

import numpy as np
from neo4j import GraphDatabase

from .pdf_processing import ArticleDoc


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
        ]
        with self.driver.session() as session:
            for stmt in statements:
                session.run(stmt, dims=vector_dimensions)

    def clear_graph(self) -> None:
        query = """
        MATCH (n)
        WHERE any(label IN labels(n) WHERE label IN ['Article', 'Author', 'Chunk', 'Token', 'Reference'])
        DETACH DELETE n
        """
        with self.driver.session() as session:
            session.run(query)

    def ingest_articles(self, articles: list[ArticleDoc]) -> None:
        chunk_texts = [chunk.text for article in articles for chunk in article.chunks]
        if not chunk_texts:
            return
        embeddings = self.embedder.encode(chunk_texts)

        emb_iter = iter(embeddings)
        with self.driver.session() as session:
            for article in articles:
                session.run(
                    """
                    MERGE (a:Article {id: $id})
                    SET a.title = $title,
                        a.title_norm = $title_norm,
                        a.year = $year,
                        a.source_path = $source_path
                    MERGE (p:Author {name_norm: $author_norm})
                    SET p.name = $author_name
                    MERGE (p)-[:WROTE]->(a)
                    """,
                    id=article.article_id,
                    title=article.title,
                    title_norm=article.normalized_title,
                    year=article.year,
                    source_path=article.source_path,
                    author_norm=article.author.lower(),
                    author_name=article.author,
                )

                for chunk in article.chunks:
                    emb = next(emb_iter)
                    session.run(
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

                    token_rows = [
                        {"value": token, "count": count}
                        for token, count in chunk.token_counts.items()
                    ]
                    if token_rows:
                        session.run(
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

                for citation in article.citations:
                    session.run(
                        """
                        MERGE (r:Reference {id: $id})
                        SET r.raw_text = $raw_text,
                            r.year = $year,
                            r.title_guess = $title_guess,
                            r.title_norm = $title_norm
                        WITH r
                        MATCH (a:Article {id: $article_id})
                        MERGE (a)-[:CITES_REFERENCE]->(r)
                        """,
                        id=citation.citation_id,
                        raw_text=citation.raw_text,
                        year=citation.year,
                        title_guess=citation.title_guess,
                        title_norm=citation.normalized_title,
                        article_id=article.article_id,
                    )

        self._link_article_citations(articles)

    def _link_article_citations(self, articles: Iterable[ArticleDoc]) -> None:
        by_title = {a.article_id: a for a in articles}
        links: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()
        for source in articles:
            for citation in source.citations:
                if not citation.normalized_title:
                    continue
                best_target = None
                best_score = 0.0
                for target in by_title.values():
                    if target.article_id == source.article_id:
                        continue
                    score = SequenceMatcher(None, citation.normalized_title, target.normalized_title).ratio()
                    year_match = citation.year is None or target.year is None or abs(citation.year - target.year) <= 1
                    if year_match and score > best_score:
                        best_score = score
                        best_target = target.article_id
                if best_target and best_score >= 0.72:
                    pair = (source.article_id, best_target)
                    seen_pairs.add(pair)
                    links.append(
                        {
                            "source": source.article_id,
                            "target": best_target,
                            "reference_id": citation.citation_id,
                            "score": round(best_score, 4),
                            "method": "reference_title_match",
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
                author_hit = target.author.lower() in source_text
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
            for target in articles:
                if target.year is None:
                    continue
                if source.article_id == target.article_id:
                    continue
                if source.author.lower() != target.author.lower():
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
                MATCH (auth:Author)-[:WROTE]->(a)
                OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                WITH c, a, auth, token_score,
                     [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out,
                     [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                RETURN c.id AS chunk_id,
                       c.text AS chunk_text,
                       c.index AS chunk_index,
                       c.page_start AS page_start,
                       c.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       auth.name AS author,
                       token_score,
                       cites_out,
                       cited_by
                ORDER BY token_score DESC
                LIMIT $limit
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
                MATCH (auth:Author)-[:WROTE]->(a)
                OPTIONAL MATCH (a)-[:CITES]->(out:Article)
                OPTIONAL MATCH (inp:Article)-[:CITES]->(a)
                WITH node, a, auth, score,
                     [x IN collect(DISTINCT out.title) WHERE x IS NOT NULL][0..5] AS cites_out,
                     [x IN collect(DISTINCT inp.title) WHERE x IS NOT NULL][0..5] AS cited_by
                RETURN node.id AS chunk_id,
                       node.text AS chunk_text,
                       node.index AS chunk_index,
                       node.page_start AS page_start,
                       node.page_end AS page_end,
                       a.id AS article_id,
                       a.title AS article_title,
                       a.year AS article_year,
                       auth.name AS author,
                       score AS vector_score,
                       cites_out,
                       cited_by
                ORDER BY vector_score DESC
                """,
                k=limit,
                embedding=vector,
            )
            return [dict(r) for r in result]
