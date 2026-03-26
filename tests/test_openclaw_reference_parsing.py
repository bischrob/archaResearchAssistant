from __future__ import annotations

from pathlib import Path

from src.rag import openclaw_structured_refs as refs
from src.rag.config import Settings
from src.rag.pdf_processing import Citation


def test_split_reference_strings_for_anystyle_uses_openclaw_agent_on_ambiguous_block(monkeypatch) -> None:
    block = "References\nFigure 1\nSmith, J. 2001. First reference. Doe, A. 2002. Second reference."

    monkeypatch.setattr(refs, "split_reference_strings_heuristic", lambda _text: ["References"])
    monkeypatch.setattr(
        refs,
        "invoke_openclaw_agent",
        lambda task, payload, settings=None, timeout=180: {
            "references": [
                "Smith, J. 2001. First reference.",
                "Doe, A. 2002. Second reference.",
            ]
        },
    )

    rows = refs.split_reference_strings_for_anystyle(block, settings=Settings())

    assert rows == [
        "Smith, J. 2001. First reference.",
        "Doe, A. 2002. Second reference.",
    ]


def test_split_reference_strings_heuristic_handles_bracketed_citekeys() -> None:
    block = """References
[ABC+22]
Kwangjun Ahn, Sebastien Bubeck. 2022. First reference.
[DEF+21]
Jane Doe. 2021. Second reference.
"""

    rows = refs.split_reference_strings_heuristic(block)

    assert len(rows) == 2
    assert rows[0].startswith("[ABC+22]")
    assert "First reference" in rows[0]
    assert rows[1].startswith("[DEF+21]")
    assert "Second reference" in rows[1]


def test_detect_section_plan_details_keeps_references_until_appendix() -> None:
    lines = [
        "Introduction",
        "Body paragraph.",
        "References",
        "[1] Alpha. 2020. First reference.",
        "[2] Beta. 2021. Second reference.",
        "APPENDIX",
        "Figure 1: Supplemental figure.",
    ]

    _headings, sections, ref_blocks = refs.detect_section_plan_details(lines, settings=Settings())

    assert ref_blocks == [2]
    assert any(section.kind == "references" and section.start_line == 2 and section.end_line == 4 for section in sections)
    assert any(section.kind == "backmatter_other" and section.start_line == 5 for section in sections)


def test_trim_reference_block_lines_with_openclaw_agent_drops_appendix_spillover(monkeypatch) -> None:
    block_lines = [
        "[AAA+23] Alice Author. 2023. First reference.",
        "[BBB+22] Bob Writer. 2022. Second reference.",
        "C.2 Example of GPT-4 visualizing IMDb data.",
        "Human: I am a Hollywood producer.",
        "AI: There are many possible ways to visualize this dataset.",
        "C:\\Zoo> dir",
        "Microsoft Windows [Version 10.0.19045.0]",
    ]

    monkeypatch.setattr(
        refs,
        "invoke_openclaw_agent",
        lambda task, payload, settings=None, timeout=180: {"last_reference_line": 1},
    )

    trimmed = refs._trim_reference_block_lines_with_openclaw_agent(block_lines, settings=Settings())

    assert trimmed == block_lines[:2]


def test_reference_block_text_keeps_clean_reference_block_without_agent(monkeypatch) -> None:
    lines = [
        "References",
        "[AAA+23] Alice Author. 2023. First reference.",
        "[BBB+22] Bob Writer. 2022. Second reference.",
    ]
    called = {"count": 0}

    def _fake_agent(task, payload, settings=None, timeout=180):
        called["count"] += 1
        return {"last_reference_line": 1}

    monkeypatch.setattr(refs, "invoke_openclaw_agent", _fake_agent)

    block = refs._reference_block_text(lines, refs.SectionSpan(start_line=0, end_line=2, kind="references"), settings=Settings())

    assert called["count"] == 0
    assert block.splitlines() == lines[1:]


def test_extract_structured_chunks_and_citations_writes_one_reference_per_line_sidecar(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "segmented.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    settings = Settings(citation_parser="openclaw_refsplit_anystyle")

    lines_with_page = [
        (1, "Introduction"),
        (1, "Body paragraph one for section-aware chunking."),
        (1, "References"),
        (1, "Smith, J. 2024. Example reference one. Jones, A. 2023. Example reference two."),
        (2, "Brown, C. 2022. Example reference three."),
    ]

    monkeypatch.setattr(refs, "_extract_lines_with_page", lambda *args, **kwargs: lines_with_page)
    monkeypatch.setattr(
        refs,
        "detect_section_plan_details",
        lambda lines, settings=None: (
            ["Introduction", "References"],
            [refs.SectionSpan(start_line=0, end_line=1, kind="body"), refs.SectionSpan(start_line=2, end_line=4, kind="references")],
            None,
        ),
    )
    monkeypatch.setattr(refs, "split_reference_strings_heuristic", lambda _text: ["References"])
    monkeypatch.setattr(
        refs,
        "invoke_openclaw_agent",
        lambda task, payload, settings=None, timeout=180: {
            "references": [
                "Smith, J. 2024. Example reference one.",
                "Jones, A. 2023. Example reference two.",
                "Brown, C. 2022. Example reference three.",
            ]
        },
    )
    monkeypatch.setattr(
        refs,
        "parse_reference_strings_with_anystyle_docker",
        lambda reference_strings, **kwargs: [
            Citation(
                citation_id=f"segmented::ref::{idx}",
                raw_text=row,
                year=2024 - idx,
                title_guess=row,
                normalized_title=row.lower(),
                source="anystyle",
            )
            for idx, row in enumerate(reference_strings)
        ],
    )

    result = refs.extract_structured_chunks_and_citations(
        pdf_path=pdf_path,
        article_id="segmented",
        settings=settings,
        chunk_size_words=32,
        chunk_overlap_words=8,
        strip_page_noise=True,
    )

    assert [c.raw_text for c in result.citations] == result.reference_strings
    assert result.reference_strings == [
        "Smith, J. 2024. Example reference one.",
        "Jones, A. 2023. Example reference two.",
        "Brown, C. 2022. Example reference three.",
    ]
    sidecar = pdf_path.with_suffix(".references.txt")
    assert sidecar.exists()
    assert sidecar.read_text(encoding="utf-8").splitlines() == result.reference_strings
