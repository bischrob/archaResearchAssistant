from src.rag.pdf_processing import Citation, build_lines_with_page, filter_citations, normalize_title


def test_build_lines_with_page_removes_repeated_headers_footers_and_page_numbers() -> None:
    page_text = [
        (
            1,
            "\n".join(
                [
                    "Journal of Field Archaeology",
                    "Article Title",
                    "Body paragraph one starts here.",
                    "Body paragraph continues.",
                    "Page 1",
                ]
            ),
        ),
        (
            2,
            "\n".join(
                [
                    "Journal of Field Archaeology",
                    "Article Title",
                    "Another body paragraph starts here.",
                    "More body text.",
                    "Page 2",
                ]
            ),
        ),
    ]

    lines = build_lines_with_page(page_text, strip_page_noise=True)
    text_only = [line for _, line in lines]

    assert "Journal of Field Archaeology" not in text_only
    assert "Article Title" not in text_only
    assert "Page 1" not in text_only
    assert "Page 2" not in text_only
    assert "Body paragraph one starts here." in text_only
    assert "Another body paragraph starts here." in text_only


def test_build_lines_with_page_can_disable_noise_stripping() -> None:
    page_text = [
        (
            1,
            "\n".join(
                [
                    "Header",
                    "Body text.",
                    "1",
                ]
            ),
        ),
    ]

    lines = build_lines_with_page(page_text, strip_page_noise=False)
    text_only = [line for _, line in lines]
    assert text_only == ["Header", "Body text.", "1"]


def test_filter_citations_removes_junk_references() -> None:
    good = Citation(
        citation_id="a::ref::0",
        raw_text="Smith 2001. A useful study.",
        year=2001,
        title_guess="A useful study",
        normalized_title=normalize_title("A useful study"),
        source="anystyle",
        author_tokens=["smith"],
    )
    junk = Citation(
        citation_id="a::ref::1",
        raw_text="Downloaded from https://example.com and terms and conditions apply.",
        year=2001,
        title_guess="Downloaded from https://example.com",
        normalized_title=normalize_title("Downloaded from https://example.com"),
        source="anystyle",
    )

    filtered = filter_citations([good, junk], min_score=0.35)

    assert len(filtered) == 1
    assert filtered[0].citation_id == "a::ref::0"
