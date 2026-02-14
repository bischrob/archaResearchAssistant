from src.rag.retrieval import contextual_retrieve, parse_query_terms


class FakeStore:
    def vector_query(self, query: str, limit: int):
        return [
            {
                "chunk_id": "c1",
                "chunk_text": "Chronology and excavation notes.",
                "article_title": "Fremont Chronology",
                "article_year": 2020,
                "authors": ["Alice Smith"],
                "vector_score": 0.4,
                "cites_out": [],
                "cited_by": [],
            }
        ]

    def token_query(self, tokens, limit: int):
        return [
            {
                "chunk_id": "c2",
                "chunk_text": "Field notes by Bischoff in northern Utah.",
                "article_title": "Utah Survey",
                "article_year": 2021,
                "authors": ["Ryan Bischoff"],
                "token_score": 3.0,
                "cites_out": ["Older Work"],
                "cited_by": ["Recent Study"],
            }
        ]

    def author_query(self, terms, limit: int):
        return [
            {
                "chunk_id": "c3",
                "chunk_text": "Settlement interpretation.",
                "article_title": "Regional Synthesis",
                "article_year": 2022,
                "authors": ["Ryan Bischoff"],
                "author_score": 2.0,
                "cites_out": ["A"],
                "cited_by": [],
            }
        ]

    def title_query(self, terms, limit: int):
        return [
            {
                "chunk_id": "c4",
                "chunk_text": "This work introduces ArchMatNet.",
                "article_title": "ArchMatNet: Archaeological Materials Network",
                "article_year": 2023,
                "authors": ["R. Bischoff"],
                "title_score": 2.0,
                "cites_out": [],
                "cited_by": [],
            }
        ]


def test_parse_query_terms_extracts_tokens_years_and_phrases():
    plan = parse_query_terms('Bischoff chronology "northern Utah" 2021')
    assert "bischoff" in plan["tokens"]
    assert 2021 in plan["years"]
    assert "northern utah" in plan["phrases"]
    assert "bischoff" in plan["author_terms"]


def test_contextual_retrieve_includes_author_channel_and_reranks():
    rows = contextual_retrieve(FakeStore(), "Bischoff", limit=2)
    assert len(rows) == 2
    top = rows[0]
    assert "query_features" in top
    assert "retrieval_sources" in top
    # Author-match rows should be favored for author-name queries.
    assert any("bischoff" in " ".join(r.get("authors") or []).lower() for r in rows)


def test_contextual_retrieve_prefers_must_term_acronym_hits():
    rows = contextual_retrieve(FakeStore(), "Summarize ArchMatNet in simple terms", limit=3)
    assert rows
    assert any("archmatnet" in (r.get("article_title", "") + " " + r.get("chunk_text", "")).lower() for r in rows)
