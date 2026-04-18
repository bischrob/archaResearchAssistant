from __future__ import annotations

from src.rag.markdown_ingest import chunk_markdown_by_headings, detect_references_section, split_reference_entries


def test_chunk_markdown_by_headings_merges_undersized_sections() -> None:
    md = "# A\nshort\n## B\nstill short text\n### C\nlong enough text " + "word " * 80
    chunks = chunk_markdown_by_headings(md, min_words=20, target_words=40, max_words=80)
    assert chunks
    assert any("A" in " ".join(chunk.heading_path) for chunk in chunks)


def test_chunk_markdown_by_headings_splits_oversized_sections() -> None:
    md = "# Big\n" + ("alpha beta gamma delta " * 220)
    chunks = chunk_markdown_by_headings(md, min_words=20, target_words=80, max_words=120)
    assert len(chunks) > 1
    assert all(chunk.token_count > 0 for chunk in chunks)


def test_detect_references_section_matches_heading_variants() -> None:
    md = "# Intro\nBody\n## Works Cited\nSmith 2020..."
    start, _ = detect_references_section(md)
    assert start is not None


def test_split_reference_entries_splits_one_per_entry() -> None:
    md = "# Intro\nBody\n## References\nSmith, J. 2020. One.\nJones, A. 2021. Two.\n"
    entries = split_reference_entries(md)
    assert len(entries) == 2
