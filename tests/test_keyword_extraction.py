from src.rag.keyword_extraction import extract_keywords
from src.rag.pdf_processing import ArticleDoc, Chunk, Section


def test_extract_keywords_has_heuristic_fallback_without_agent():
    article = ArticleDoc(article_id='a1', title='Forest drought resilience in pinon pine ecosystems', normalized_title='forest drought resilience in pinon pine ecosystems', year=2024, author='Smith', authors=['Smith'], citekey=None, paperpile_id=None, doi=None, journal='Ecology Letters', publisher=None, source_path='/tmp/a1.pdf', chunks=[Chunk(chunk_id='c1', index=0, text='Forest drought resilience and mortality under warming climate', tokens=['forest','drought','resilience','mortality','warming','climate'], token_counts={'drought':4,'resilience':3,'forest':2,'mortality':2,'warming':1,'climate':1}, page_start=1, page_end=2, section_type='body'), Chunk(chunk_id='c2', index=1, text='Pinon pine ecosystems and forest recovery', tokens=['pinon','pine','ecosystems','forest','recovery'], token_counts={'ecosystems':3,'pine':2,'forest':1,'recovery':1}, page_start=2, page_end=3, section_type='body')], citations=[], sections=[Section(section_id='s1', kind='body', start_line=0, end_line=10, page_start=1, page_end=3, heading='Introduction')])
    keywords, audit = extract_keywords(article)
    assert keywords
    assert audit['keyword_count'] == len(keywords)
    assert audit['method'] in {'heuristic', 'openclaw_agent_plus_heuristic'}
    assert any(('forest' in k.normalized_value) or ('drought' in k.normalized_value) for k in keywords)
