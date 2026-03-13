import pytest

from src.rag import llm_answer


def test_preprocess_search_query_uses_qwen_backend(monkeypatch) -> None:
    monkeypatch.setenv("QUERY_PREPROCESS_BACKEND", "qwen")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_answer,
        "generate_query_directive_with_qwen",
        lambda question, settings=None: (
            "authors: Binford | years: 1962 | title_terms: archaeology as anthropology | content_terms: method theory"
        ),
    )

    rewritten = llm_answer.preprocess_search_query("What did Binford argue in 1962?")

    assert rewritten == "Binford 1962 archaeology as anthropology method theory"


def test_preprocess_search_query_openai_default_requires_api_key(monkeypatch) -> None:
    monkeypatch.setenv("QUERY_PREPROCESS_BACKEND", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OpenAPIKey", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is not set"):
        llm_answer.preprocess_search_query("test")
