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


def test_ask_openclaw_grounded_passes_through_cited_answer_with_relevance_filter(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_answer,
        'invoke_openclaw_agent',
        lambda task, payload, settings=None, timeout=120: {
            'answer': 'Supported answer [C1]',
            'relevant_citation_ids': ['C1'],
            'excluded_citation_ids': ['C2'],
            'relevance_summary': 'Used 1 of 2 retrieved results after relevance filtering.',
            'synthesis_status': 'succeeded',
        },
    )
    rows = [
        {'chunk_id': 'c1', 'chunk_text': 'Evidence text about Binford and archaeology.', 'article_title': 'Paper A', 'article_year': 2020},
        {'chunk_id': 'c2', 'chunk_text': 'Completely unrelated astrophysics passage.', 'article_title': 'Paper B', 'article_year': 2019},
    ]
    result = llm_answer.ask_openclaw_grounded('What did Binford argue about archaeology?', rows)
    assert result['answer'] == 'Supported answer [C1]'
    assert result['method'] == 'openclaw_agent'
    assert result['synthesis_status'] == 'succeeded'
    assert result['fallback_reason'] is None
    assert [c['citation_id'] for c in result['used_citations']] == ['C1']
    assert [c['citation_id'] for c in result['relevant_citations']] == ['C1']
    assert [c['citation_id'] for c in result['excluded_citations']] == ['C2']
    assert result['relevance_summary'].startswith('Used 1 of 2')


def test_ask_openclaw_grounded_rejects_answer_that_cites_irrelevant_results(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_answer,
        'invoke_openclaw_agent',
        lambda *args, **kwargs: {
            'answer': 'Bad mixed answer [C1] [C2]',
            'relevant_citation_ids': ['C1'],
            'excluded_citation_ids': ['C2'],
            'relevance_summary': 'Used 1 of 2 retrieved results after relevance filtering.',
            'synthesis_status': 'succeeded',
        },
    )
    rows = [
        {'chunk_id': 'c1', 'chunk_text': 'Projectile point details from Arizona context.', 'article_title': 'Paper A', 'article_year': 2020},
        {'chunk_id': 'c2', 'chunk_text': 'Unrelated ocean chemistry details.', 'article_title': 'Paper B', 'article_year': 2021},
    ]
    result = llm_answer.ask_openclaw_grounded('What projectile points are found in Arizona?', rows)
    assert result['method'] == 'deterministic_fallback'
    assert result['fallback_reason'] == 'answer_cites_irrelevant_results'


def test_ask_openclaw_grounded_failure_is_explicit_when_no_relevant_evidence(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_answer,
        'invoke_openclaw_agent',
        lambda *args, **kwargs: None,
    )
    rows = [{'chunk_id': 'c1', 'chunk_text': 'Ocean salinity measurements from Atlantic transects.', 'article_title': 'Paper A', 'article_year': 2020}]
    result = llm_answer.ask_openclaw_grounded('What projectile points are found in Arizona?', rows)
    assert result['method'] == 'deterministic_fallback'
    assert result['synthesis_status'] == 'irrelevant_context'
    assert result['fallback_reason'] == 'invalid_agent_response'
    assert result['answer'] == 'None of the retrieved evidence appears relevant enough to answer this question.'
    assert result['used_citations'] == []
    assert result['relevant_citations'] == []
    assert result['excluded_citations'][0]['citation_id'] == 'C1'
    assert result['evidence_snippets'] == []


def test_preprocess_search_query_dedupes_duplicate_terms_from_agent_directive(monkeypatch) -> None:
    monkeypatch.setenv('QUERY_PREPROCESS_BACKEND', 'openclaw_agent')
    monkeypatch.setattr(
        llm_answer,
        'invoke_openclaw_agent',
        lambda task, payload, settings=None, timeout=60: {
            'directive': 'authors: Hohokam | years: none | title_terms: Hohokam projectile points | content_terms: Hohokam typology Arizona'
        },
    )
    rewritten = llm_answer.preprocess_search_query('Hohokam projectile points')
    assert rewritten == 'Hohokam projectile points typology Arizona'


def test_preprocess_search_query_adds_archaeology_aware_expansion_in_fallback(monkeypatch) -> None:
    monkeypatch.setenv('QUERY_PREPROCESS_BACKEND', 'openclaw_agent')
    monkeypatch.setattr(llm_answer, 'invoke_openclaw_agent', lambda *args, **kwargs: None)
    rewritten = llm_answer.preprocess_search_query('Hohokam projectile points')
    tokens = set(rewritten.lower().split())
    assert {'hohokam', 'projectile', 'points'} <= tokens
    assert 'arizona' in tokens
    assert 'typology' in tokens
    assert 'lithic' in tokens
    assert len(rewritten.split()) == len(tokens)


def test_preprocess_search_query_rejects_bad_agent_rewrite_and_falls_back_to_original(monkeypatch) -> None:
    monkeypatch.setenv('QUERY_PREPROCESS_BACKEND', 'openclaw_agent')
    monkeypatch.setattr(
        llm_answer,
        'invoke_openclaw_agent',
        lambda *args, **kwargs: {'directive': 'authors: none | years: none | title_terms: archaeology overview | content_terms: paper summary'},
    )
    rewritten = llm_answer.preprocess_search_query('Hohokam projectile points in Arizona')
    assert rewritten == 'Hohokam projectile points in Arizona'


def test_gate_rows_for_synthesis_excludes_domain_mismatch() -> None:
    rows = [
        {'chunk_id': 'c1', 'chunk_text': 'Hohokam projectile point typology in Arizona sites.', 'article_title': 'Hohokam Lithics', 'article_year': 2020},
        {'chunk_id': 'c2', 'chunk_text': 'General Hohokam irrigation and settlement patterns.', 'article_title': 'Hohokam Settlements', 'article_year': 2021},
        {'chunk_id': 'c3', 'chunk_text': 'Projectile point chronologies from Great Basin contexts in Utah.', 'article_title': 'Utah Projectile Points', 'article_year': 2019},
    ]
    usable, excluded, summary = llm_answer.gate_rows_for_synthesis('Hohokam projectile points in Arizona', rows)
    assert [row['chunk_id'] for row in usable] == ['c1']
    assert {row['chunk_id'] for row in excluded} == {'c2', 'c3'}
    assert 'hard relevance gating' in summary
