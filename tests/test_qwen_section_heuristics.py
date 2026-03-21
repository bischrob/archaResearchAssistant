from src.rag.qwen_structured_refs import (
    _build_typed_sections,
    _heading_candidates,
    _heuristic_reference_starts,
    _toc_mapped_heading_candidates,
)


def test_heuristic_reference_starts_ignores_toc_works_cited() -> None:
    lines = [
        "Contents",
        "Conclusions.",
        ".114",
        "Acknowledgements..",
        ".116",
        "Works Cited",
        ".117",
        "Tables.",
        "..124",
        "Figures .",
        ".127",
        "APPENDIX C. HYDROCLIMATIC STABILITY,",
        "Some prose line that starts the document",
        "Works Cited",
        "Allen, C.D. and D.D. Breshears. (1998) Drought-induced shift...",
    ]

    assert _heuristic_reference_starts(lines) == [13]


def test_build_typed_sections_supports_multiple_reference_blocks_and_front_matter() -> None:
    lines = [
        "Title Page",
        "CONTENTS",
        "PREFACE",
        "Body start",
        "CHAPTER 1",
        "Some body text",
        "Works Cited",
        "Reference A",
        "APPENDIX A",
        "Appendix text",
        "Works Cited",
        "Reference B",
    ]

    sections = _build_typed_sections(
        lines,
        heading_indices=[0, 1, 2, 4, 6, 8, 10],
        reference_starts=[6, 10],
        reference_start=6,
        min_section_lines=1,
    )

    assert [(s.start_line, s.end_line, s.kind) for s in sections] == [
        (0, 3, "frontmatter"),
        (4, 5, "body"),
        (6, 7, "references"),
        (8, 9, "backmatter_other"),
        (10, 11, "references"),
    ]


def test_toc_candidates_map_to_later_real_headings() -> None:
    lines = [
        "Title Page",
        "CONTENTS",
        "INTRODUCTION ................................ 1",
        "METHODS ..................................... 7",
        "REFERENCES ................................. 22",
        "Some front matter text",
        "INTRODUCTION",
        "Body text",
        "METHODS",
        "More body text",
        "REFERENCES",
        "Ref A",
    ]

    assert _toc_mapped_heading_candidates(lines) == [
        (6, "INTRODUCTION"),
        (8, "METHODS"),
        (10, "REFERENCES"),
    ]


def test_heading_candidates_prefer_later_toc_mapped_occurrences() -> None:
    lines = [
        "Title Page",
        "CONTENTS",
        "INTRODUCTION ................................ 1",
        "METHODS ..................................... 7",
        "REFERENCES ................................. 22",
        "Some front matter text",
        "INTRODUCTION",
        "Body text",
        "METHODS",
        "More body text",
        "REFERENCES",
        "Ref A",
    ]

    candidates = _heading_candidates(lines)
    assert (2, "INTRODUCTION ................................ 1") not in candidates
    assert (3, "METHODS ..................................... 7") not in candidates
    assert (6, "INTRODUCTION") in candidates
    assert (8, "METHODS") in candidates


def test_appendix_stops_reference_block() -> None:
    lines = [
        "Title Page",
        "INTRODUCTION",
        "Body",
        "REFERENCES",
        "Ref A",
        "APPENDIX A. DATA",
        "Appendix text",
    ]
    sections = _build_typed_sections(
        lines,
        heading_indices=[0, 1, 3, 5],
        reference_starts=[3],
        reference_start=3,
        min_section_lines=1,
    )
    assert [(s.start_line, s.end_line, s.kind) for s in sections] == [
        (0, 0, "frontmatter"),
        (1, 2, "body"),
        (3, 4, "references"),
        (5, 6, "backmatter_other"),
    ]
