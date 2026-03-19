from src.rag import metadata_provider
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


def test_find_metadata_for_pdf_prefers_path_hint_over_basename() -> None:
    idx = MetadataIndex(
        backend='zotero',
        by_basename={'shared.pdf': {'title': 'basename'}},
        by_normalized={},
        by_path_normalized={'/library/one/shared.pdf': {'title': 'path'}},
    )

    assert find_metadata_for_pdf(idx, 'shared.pdf', '/library/one/shared.pdf')['title'] == 'path'


def test_find_metadata_for_pdf_prefers_path_hint_over_basename_and_normalized() -> None:
    idx = MetadataIndex(
        backend='zotero',
        by_basename={'shared.pdf': {'title': 'basename'}},
        by_normalized={'shared': {'title': 'normalized'}},
        by_path_normalized={'/library/one/shared.pdf': {'title': 'path'}},
    )

    assert find_metadata_for_pdf(idx, 'shared.pdf', '/library/one/shared.pdf')['title'] == 'path'
    assert find_metadata_for_pdf(idx, 'shared-!!.pdf', '/library/one/shared.pdf')['title'] == 'path'
    assert find_metadata_for_pdf(idx, 'missing.pdf', '/library/one/shared.pdf')['title'] == 'path'


def test_build_index_prefers_higher_scoring_duplicate_metadata_entry() -> None:
    idx = metadata_provider._build_index(
        'zotero',
        [
            {'attachment_path': '/tmp/shared.pdf', 'title': 'low'},
            {
                'attachment_path': '/tmp/shared.pdf',
                'title': 'high',
                'year': 2024,
                'citekey': 'Shared2024',
                'paperpile_id': 'pp-1',
                'doi': '10.1000/example',
                'journal': 'Journal',
                'publisher': 'Publisher',
                'authors': ['A', 'B'],
            },
        ],
    )

    assert idx.by_basename['shared.pdf']['title'] == 'high'
    assert idx.by_path_normalized['/tmp/shared.pdf']['title'] == 'high'


def test_metadata_title_year_key_formats() -> None:
    key = metadata_title_year_key({'title': 'My Great Paper: A Study', 'year': '2020'})
    assert key == 'my great paper a study|2020'
    accented = metadata_title_year_key({'title': 'Fábrega-Álvarez: Pathwáys', 'year': 2022})
    assert accented == 'fabrega alvarez pathways|2022'
    assert metadata_title_year_key({'title': '', 'year': 2020}) is None
    assert metadata_title_year_key({'title': 'abc', 'year': None}) is None
