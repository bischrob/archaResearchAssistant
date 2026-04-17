from src.rag.anystyle_refs import parse_anystyle_json_payload, parse_reference_entries_resilient
from src.rag.pdf_processing import Citation


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


def test_parse_anystyle_json_payload_uses_raw_reference_text_when_provided() -> None:
    payload = [
        {"title": ["Good Entry"], "date": ["1999"]},
    ]
    raw_refs = ["Abbott, D. R. 1999. Good Entry. Tucson."]

    citations = parse_anystyle_json_payload(payload, article_id="doc", raw_references=raw_refs)

    assert len(citations) == 1
    assert citations[0].raw_text == raw_refs[0]
    assert citations[0].title_guess == "Good Entry"


def test_parse_reference_entries_resilient_records_failures_and_continues(monkeypatch) -> None:
    def fake_parse(references, **kwargs):
        if "Bad" in references[0]:
            raise RuntimeError("parse failed")
        return [
            Citation(
                citation_id="x::ref::0",
                raw_text=references[0],
                year=2020,
                title_guess="Good",
                normalized_title="good",
                source="anystyle",
            )
        ]

    monkeypatch.setattr("src.rag.anystyle_refs.parse_reference_strings_with_anystyle_docker", fake_parse)
    citations, failures = parse_reference_entries_resilient(
        ["Good Ref 2020", "Bad Ref 2021", "Another Good 2022"],
        article_id="doc",
    )
    assert len(citations) == 2
    assert len(failures) == 1
    assert "parse failed" in failures[0]["error"]
