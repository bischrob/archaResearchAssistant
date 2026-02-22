from src.rag.anystyle_refs import parse_anystyle_json_payload


def test_parse_anystyle_json_payload_extracts_core_fields() -> None:
    payload = [
        {
            "title": ["The House of Mirth"],
            "date": ["1958"],
            "author": [{"family": "Chang", "given": "K. C."}],
        },
        {
            "container-title": ["Journal of Archaeology"],
            "date": ["Spring 2004"],
        },
    ]

    citations = parse_anystyle_json_payload(payload, article_id="chang1958-paper")

    assert len(citations) == 2
    assert citations[0].citation_id == "chang1958-paper::ref::0"
    assert citations[0].title_guess == "The House of Mirth"
    assert citations[0].year == 1958
    assert citations[0].normalized_title == "the house of mirth"
    assert citations[0].source == "anystyle"
    assert citations[0].author_tokens == ["chang"]
    assert citations[1].title_guess == "Journal of Archaeology"
    assert citations[1].year == 2004


def test_parse_anystyle_json_payload_skips_non_dict_rows() -> None:
    payload = [
        "bad",
        {"title": ["Good Entry"], "date": ["1999"]},
        42,
    ]

    citations = parse_anystyle_json_payload(payload, article_id="doc")

    assert len(citations) == 1
    assert citations[0].citation_id == "doc::ref::1"
    assert citations[0].title_guess == "Good Entry"
