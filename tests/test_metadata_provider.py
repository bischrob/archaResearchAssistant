from src.rag.metadata_provider import MetadataIndex, find_metadata_for_pdf, metadata_title_year_key


def test_find_metadata_for_pdf_uses_path_and_filename() -> None:
    idx = MetadataIndex(
        backend='zotero',
        by_basename={'a.pdf': {'title': 'A'}},
        by_normalized={'a': {'title': 'A-norm'}},
        by_path_normalized={'/x/y/a.pdf': {'title': 'A-path'}},
    )

    assert find_metadata_for_pdf(idx, 'a.pdf')['title'] == 'A'
    assert find_metadata_for_pdf(idx, 'A.PDF')['title'] == 'A'
    assert find_metadata_for_pdf(idx, 'a-!!.pdf')['title'] == 'A-norm'
    assert find_metadata_for_pdf(idx, 'missing.pdf', '/x/y/a.pdf')['title'] == 'A-path'


def test_metadata_title_year_key_formats() -> None:
    key = metadata_title_year_key({'title': 'My Great Paper: A Study', 'year': '2020'})
    assert key == 'my great paper a study|2020'
    assert metadata_title_year_key({'title': '', 'year': 2020}) is None
    assert metadata_title_year_key({'title': 'abc', 'year': None}) is None
