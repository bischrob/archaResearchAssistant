import threading
import time

import src.rag.retrieval as retrieval
from src.rag.retrieval import article_claim_match, contextual_retrieve, parse_query_terms


class FakeStore:
    def vector_query(self, query: str, limit: int):
        return [
            {
                "chunk_id": "c1",
                "article_id": "a1",
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
                "article_id": "a2",
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
                "article_id": "a3",
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
                "article_id": "a4",
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


class PaperScopeStore:
    def vector_query(self, query: str, limit: int):
        return [
            {
                "chunk_id": "a1-c1",
                "article_id": "a1",
                "chunk_text": "Chronology and fieldwork context.",
                "article_title": "Fremont Chronology",
                "article_year": 2020,
                "authors": ["Alice Smith"],
                "vector_score": 0.65,
                "cites_out": [],
                "cited_by": [],
            },
            {
                "chunk_id": "a1-c2",
                "article_id": "a1",
                "chunk_text": "Additional chronology details for Fremont sites.",
                "article_title": "Fremont Chronology",
                "article_year": 2020,
                "authors": ["Alice Smith"],
                "vector_score": 0.62,
                "cites_out": [],
                "cited_by": [],
            },
            {
                "chunk_id": "a2-c1",
                "article_id": "a2",
                "chunk_text": "Utah basin chronology synthesis and discussion.",
                "article_title": "Utah Basin Synthesis",
                "article_year": 2021,
                "authors": ["Bob Jones"],
                "vector_score": 0.58,
                "cites_out": [],
                "cited_by": [],
            },
        ]

    def token_query(self, tokens, limit: int):
        return [
            {
                "chunk_id": "a1-c1",
                "article_id": "a1",
                "chunk_text": "Chronology and fieldwork context.",
                "article_title": "Fremont Chronology",
                "article_year": 2020,
                "authors": ["Alice Smith"],
                "token_score": 4.0,
                "cites_out": [],
                "cited_by": [],
            },
            {
                "chunk_id": "a2-c1",
                "article_id": "a2",
                "chunk_text": "Utah basin chronology synthesis and discussion.",
                "article_title": "Utah Basin Synthesis",
                "article_year": 2021,
                "authors": ["Bob Jones"],
                "token_score": 3.5,
                "cites_out": [],
                "cited_by": [],
            },
        ]

    def author_query(self, terms, limit: int):
        return []

    def title_query(self, terms, limit: int):
        return []


def test_contextual_retrieve_paper_scope_returns_unique_papers():
    rows = contextual_retrieve(
        PaperScopeStore(),
        "fremont chronology",
        limit=2,
        limit_scope="papers",
        chunks_per_paper=2,
    )
    assert len(rows) == 2
    assert len({r.get("article_id") for r in rows}) == 2
    assert all(r.get("result_scope") == "paper" for r in rows)
    assert all(len(r.get("highlight_chunks") or []) <= 2 for r in rows)


def test_contextual_retrieve_score_threshold_keeps_all_relevant_rows_above_cutoff():
    rows = contextual_retrieve(FakeStore(), "Bischoff", limit=1, score_threshold=1.0)
    assert rows
    assert all(row.get("rerank_score", 0.0) >= 1.0 for row in rows)
    assert len(rows) >= 1


def test_contextual_retrieve_score_threshold_falls_back_to_top_limit_when_nothing_matches():
    rows = contextual_retrieve(FakeStore(), "Bischoff", limit=2, score_threshold=9.9)
    assert len(rows) == 2


class SlowVectorStore(FakeStore):
    def __init__(self):
        self.vector_started = threading.Event()

    def vector_query(self, query: str, limit: int):
        self.vector_started.set()
        time.sleep(0.25)
        return super().vector_query(query, limit)


def test_contextual_retrieve_falls_back_when_vector_query_times_out(monkeypatch):
    store = SlowVectorStore()
    monkeypatch.setattr(retrieval, "_VECTOR_QUERY_TIMEOUT_SECONDS", 0.05)

    rows = contextual_retrieve(store, "Bischoff", limit=2)

    assert store.vector_started.is_set()
    assert len(rows) == 2
    assert all("vector" not in (row.get("retrieval_sources") or []) for row in rows)
    assert any("token" in (row.get("retrieval_sources") or []) for row in rows)


class ArticleMatchStore:
    def article_chunks_by_citekey(self, citekey: str):
        if citekey != "qi2025llms":
            return None
        return {
            "article_id": "a1",
            "article_title": "Large Language and Multimodal Models in Archaeological Science: A Review",
            "article_year": 2025,
            "article_citekey": "qi2025llms",
            "article_doi": None,
            "article_source_path": "/tmp/qi2025.pdf",
            "authors": ["Qi", "Wen"],
            "chunks": [
                {
                    "id": "c1",
                    "index": 0,
                    "page_start": 1,
                    "page_end": 1,
                    "text": "This review surveys large language and multimodal models in archaeological science, including remote sensing, text analysis, and artifact studies.",
                },
                {
                    "id": "c2",
                    "index": 1,
                    "page_start": 10,
                    "page_end": 10,
                    "text": "References\nSmith 2020. Example title. doi:10.1000/x.\nJones 2021. Another title. doi:10.1000/y.",
                },
            ],
        }


def test_article_claim_match_prefers_supporting_content_over_reference_like_chunk():
    result = article_claim_match(
        ArticleMatchStore(),
        "qi2025llms",
        "Qi and Wen 2025 review large language and multimodal models in archaeological science",
        top_k=2,
    )
    assert result["ok"] is True
    assert result["classification"] in {"direct_support", "adjacent_or_partial_support"}
    assert result["supporting_chunks"][0]["chunk_id"] == "c1"
    assert result["supporting_chunks"][0]["support_score"] > result["supporting_chunks"][1]["support_score"]


def test_article_claim_match_returns_not_supported_for_weak_match():
    result = article_claim_match(
        ArticleMatchStore(),
        "qi2025llms",
        "This source establishes Indigenous data governance in Canadian archaeology",
        top_k=1,
    )
    assert result["ok"] is True
    assert result["classification"] == "not_supported"


class ContradictionStore:
    def article_chunks_by_citekey(self, citekey: str):
        if citekey != "draftnepa":
            return None
        return {
            "article_id": "a2",
            "article_title": "DraftNEPABench: A Benchmark for Drafting NEPA Document Sections with Coding Agents",
            "article_year": 2026,
            "article_citekey": "draftnepa",
            "article_doi": None,
            "article_source_path": "/tmp/draftnepa.pdf",
            "authors": ["Acharya"],
            "chunks": [
                {
                    "id": "c1",
                    "index": 0,
                    "page_start": 8,
                    "page_end": 8,
                    "text": "Overall, automated evaluation can provide useful comparative signals for long-form generation but remains complementary to expert human review in NEPA drafting tasks.",
                }
            ],
        }


def test_article_claim_match_penalizes_contradiction_and_missing_archaeology_domain():
    result = article_claim_match(
        ContradictionStore(),
        "draftnepa",
        "Archaeology already has mature evidence that coding agents can reliably draft archaeological regulatory text without substantial human review.",
        top_k=1,
    )
    assert result["ok"] is True
    assert result["classification"] == "not_supported"
    features = result["supporting_chunks"][0]["support_features"]
    assert features["domain_penalty"] > 0
    assert features["contradiction_penalty"] > 0


def test_parse_query_terms_marks_archaeology_domain_terms_as_required():
    plan = parse_query_terms('Hohokam projectile points in Arizona')
    assert 'hohokam' in plan['must_terms']
    assert 'arizona' in plan['domain_terms']
    assert 'projectile' in plan['domain_terms']
    assert 'hohokam' in plan['anchor_terms']
    assert 'arizona' in plan['anchor_terms']


class AnchorFilteringStore:
    def vector_query(self, query: str, limit: int):
        return []

    def token_query(self, tokens, limit: int):
        return [
            {
                'chunk_id': 'irrelevant-1',
                'article_id': 'irrelevant-article',
                'chunk_text': 'Projectile points and chronology in Utah field survey data.',
                'article_title': 'General Projectile Point Survey',
                'article_year': 2020,
                'authors': ['Noise Author'],
                'token_score': 20.0,
                'cites_out': [],
                'cited_by': [],
            },
            {
                'chunk_id': 'relevant-1',
                'article_id': 'relevant-article',
                'chunk_text': 'Hohokam projectile points in Arizona show regional variation.',
                'article_title': 'Hohokam Projectile Points in Arizona',
                'article_year': 2019,
                'authors': ['Relevant Author'],
                'token_score': 8.0,
                'cites_out': [],
                'cited_by': [],
            },
        ]

    def author_query(self, terms, limit: int):
        return []

    def title_query(self, terms, limit: int):
        return []


def test_contextual_retrieve_archaeology_anchor_terms_filter_generic_false_positives():
    rows = contextual_retrieve(
        AnchorFilteringStore(),
        'Hohokam projectile points in Arizona',
        limit=2,
        limit_scope='papers',
        chunks_per_paper=1,
    )
    assert rows
    assert rows[0]['article_id'] == 'relevant-article'
    assert all(row['article_id'] != 'irrelevant-article' for row in rows)
