from src.rag import llm_answer


def test_preprocess_search_query_uses_openclaw_agent_backend(monkeypatch) -> None:
    monkeypatch.setenv('QUERY_PREPROCESS_BACKEND', 'openclaw_agent')
    monkeypatch.setattr(llm_answer, 'invoke_openclaw_agent', lambda task, payload, settings=None, timeout=60: {'directive': 'authors: Binford | years: 1962 | title_terms: archaeology as anthropology | content_terms: method theory'})
    rewritten = llm_answer.preprocess_search_query('What did Binford argue in 1962?')
    assert rewritten == 'Binford 1962 archaeology as anthropology method theory'


def test_preprocess_search_query_has_deterministic_fallback(monkeypatch) -> None:
    monkeypatch.setenv('QUERY_PREPROCESS_BACKEND', 'openclaw_agent')
    monkeypatch.setattr(llm_answer, 'invoke_openclaw_agent', lambda *args, **kwargs: None)
    rewritten = llm_answer.preprocess_search_query('What did Binford argue in 1962?')
    assert 'Binford' in rewritten
    assert '1962' in rewritten
