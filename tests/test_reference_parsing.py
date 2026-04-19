from __future__ import annotations

from src.rag.config import Settings
from src.rag.reference_parsing import (
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
