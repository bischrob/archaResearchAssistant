from __future__ import annotations

from src.rag.config import Settings
from src.rag.reference_parsing import (
    _extract_authors_from_text,
    detect_reference_section_from_lines,
    detect_reference_sections_from_lines,
    parse_reference_entries,
    split_references_from_lines,
)


def test_headingless_bibliography_tail_starts_after_prose() -> None:
    lines = [
        "Discussion paragraph mentioning 2026 in prose but not a citation.",
        "Another narrative line.",
        "Anthropic. 2026. Claude Code Overview.",
        "",
        "Asher, Samuel G. Z., Janet Malzahn, and Andrew B. Hall. 2026. Do Claude Code and Codex p-Hack?",
        "",
        "Bender, Emily M., Timnit Gebru, Angelina McMillan-Major, and Shmargaret Shmitchell. 2021. On the Dangers of Stochastic Parrots.",
    ]
    detection = detect_reference_section_from_lines(lines)
    assert detection.start_line == 2
    assert detection.method == "tail_cluster"


def test_split_references_merges_doi_continuation_lines() -> None:
    lines = [
        "Cobb, Hannah. 2023. Large Language Models and Generative AI, Oh My! Advances in Archaeological Practice 11(3):363-369.",
        "https://doi.org/10.1017/aap.2023.20.",
        "UNESCO. 2023. Guidance for Generative AI in Education and Research. UNESCO.",
        "https://unesdoc.unesco.org/example",
        "OpenAI. 2025. Introducing Codex.",
    ]
    split = split_references_from_lines(lines)
    assert len(split.entries) == 3
    assert "doi.org/10.1017/aap.2023.20" in split.entries[0]
    assert "unesdoc.unesco.org" in split.entries[1]


def test_parse_reference_entries_rejects_doi_only_lines_and_flags_review() -> None:
    citations, failures = parse_reference_entries(
        [
            "https://doi.org/10.1016/j.culher.2024.11.020.",
            "International Association of Scientific, Technical and Medical Publishers. 2023. Generative AI in Scholarly Communications. STM.",
        ],
        article_id="doc",
        settings=Settings(citation_parser="heuristic"),
        parser_mode="heuristic",
        split_confidence=0.75,
    )
    assert len(citations) == 1
    assert citations[0].title_guess == "Generative AI in Scholarly Communications"
    assert citations[0].parse_method == "heuristic"
    assert citations[0].parse_confidence is not None
    assert any(f["error"] == "invalid_reference_text" for f in failures)


def test_hybrid_llm_mode_falls_back_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    citations, failures = parse_reference_entries(
        ["OpenAI. 2025. Introducing Codex."],
        article_id="doc",
        settings=Settings(citation_parser="hybrid_llm"),
        parser_mode="hybrid_llm",
        split_confidence=0.8,
    )
    assert len(citations) == 1
    assert any(f["error"] == "missing_openai_api_key" for f in failures)


def test_detect_multiple_reference_sections_in_edited_volume() -> None:
    lines = [
        "# Chapter One",
        "Body text",
        "## References",
        "Smith, J. 2020. One.",
        "# Chapter Two",
        "More body",
        "## Bibliography",
        "Jones, A. 2021. Two.",
    ]
    spans = detect_reference_sections_from_lines(lines)
    assert [(s.start_line, s.end_line) for s in spans] == [(2, 3), (6, 7)]


def test_split_references_collects_multiple_reference_sections() -> None:
    lines = [
        "# Chapter One",
        "Body text",
        "## References",
        "Smith, J. 2020. One.",
        "# Chapter Two",
        "More body",
        "## Bibliography",
        "Jones, A. 2021. Two.",
    ]
    split = split_references_from_lines(lines)
    assert len(split.entries) == 2
    assert split.entries[0] == "Smith, J. 2020. One."
    assert split.entries[1] == "Jones, A. 2021. Two."


def test_split_references_splits_inline_numbered_references_and_strips_figure_noise() -> None:
    lines = [
        "## References",
        "![img](images/foo.png)",
        "Figure 1. Not a citation.",
        "[6] Smith, J. 2020. One. [7] Jones, A. 2021. Two.",
    ]
    split = split_references_from_lines(lines)
    assert split.entries == ["[6] Smith, J. 2020. One.", "[7] Jones, A. 2021. Two."]


def test_parse_reference_entries_splits_merged_author_year_entries() -> None:
    citations, failures = parse_reference_entries(
        [
            "Brandsen, Alex. 2024. First Title. https://doi.org/10.1000/first Carroll, Sarah. 2025. Second Title. https://doi.org/10.1000/second"
        ],
        article_id="doc",
        settings=Settings(citation_parser="heuristic"),
        parser_mode="heuristic",
        split_confidence=0.75,
    )
    assert len(citations) == 2
    assert citations[0].title_guess == "First Title"
    assert citations[1].title_guess == "Second Title"
    assert any(f["kind"] == "split_merged_author_year_entry" for f in failures)


def test_extract_authors_from_text_normalizes_inverted_single_author_name() -> None:
    authors = _extract_authors_from_text(
        "Morss, Noel 1931 The Ancient Culture of the Fremont River in Utah."
    )
    assert authors == ["Noel Morss"]


def test_extract_authors_from_text_handles_mixed_inverted_and_direct_names() -> None:
    authors = _extract_authors_from_text(
        "Bender, Emily M., Timnit Gebru, Angelina McMillan-Major, and Shmargaret Shmitchell. 2021. On the Dangers of Stochastic Parrots."
    )
    assert authors == [
        "Emily M. Bender",
        "Timnit Gebru",
        "Angelina McMillan-Major",
        "Shmargaret Shmitchell",
    ]


def test_extract_authors_from_text_handles_multiple_inverted_authors_with_initials() -> None:
    authors = _extract_authors_from_text(
        "Linse, Angela R., Reilly, Michael V., Kohler, Timothy A., 1992. Excavations in Area 1 of Burnt Mesa Pueblo."
    )
    assert authors == [
        "Angela R. Linse",
        "Michael V. Reilly",
        "Timothy A Kohler",
    ]


def test_extract_authors_from_text_handles_multiword_family_name_with_initial() -> None:
    authors = _extract_authors_from_text(
        "Bliege Bird, R., Smith, E.A., Bird, D.W., 2005. Signaling theory, strategic interaction, and symbolic capital."
    )
    assert authors == [
        "R. Bliege Bird",
        "E.A. Smith",
        "D.W Bird",
    ]


def test_extract_authors_from_text_stops_before_place_publisher_leakage() -> None:
    authors = _extract_authors_from_text(
        "[55] Gardin, J.-C., Archaeological constructs : an aspect of theoretical archaeology, Cambridge; New York: Cambridge University Press, 1980"
    )
    assert authors == ["J.-C. Gardin"]


def test_extract_authors_from_text_salvages_initials_before_editor_suffix() -> None:
    authors = _extract_authors_from_text(
        "[51] Trant, J., Curating collections knowledge: museums on the cyberinfrastructure, in: Marty, P.F, Jones, B.K. (Eds.), Museum Informatics: People, Information, and Technology in Museums, New York & London: Routledge, 2007"
    )
    assert authors == ["J. Trant"]


def test_extract_authors_from_text_handles_abbreviated_given_initials() -> None:
    authors = _extract_authors_from_text(
        "[31] Adhikari, K., Reales, G., Smith, A.J.P., et al.: A genome-wide association study identifies multiple loci for variation in human ear morphology, 2015"
    )
    assert authors == [
        "K. Adhikari",
        "G. Reales",
        "A.J.P. Smith",
    ]


def test_extract_authors_from_text_keeps_multiple_initial_authors_before_title_text() -> None:
    authors = _extract_authors_from_text(
        "[44] Viola, P., Jones, M.: Rapid object detection using a boosted cascade of simple features. Int. J. Comput. Vis. 57(2), 137-154 (2004)."
    )
    assert authors == [
        "P. Viola",
        "M. Jones",
    ]


def test_extract_authors_from_text_keeps_direct_initials_name_before_title_and_publisher() -> None:
    authors = _extract_authors_from_text(
        "[120] D.W. Thompson, On Growth and Form, Cambridge University Press, Cambridge, 1917."
    )
    assert authors == ["D.W. Thompson"]


def test_extract_authors_from_text_drops_trailing_middle_initial_fragment() -> None:
    authors = _extract_authors_from_text(
        "Broughton, Jack, M., and Frank E. Bayham 2002 Showing Off, Foraging Models, and the Ascendance of Large Game Hunting in the California Middle Archaic."
    )
    assert authors == [
        "Jack Broughton",
        "Frank E. Bayham",
    ]
