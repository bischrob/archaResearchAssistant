import json
from pathlib import Path

from src.rag.paperpile_metadata import find_metadata_for_pdf, load_paperpile_index


def test_load_paperpile_index_maps_attachment_basename(tmp_path: Path) -> None:
    payload = [
        {
            "_id": "abc123",
            "title": "Example Paper",
            "citekey": "Doe2021-ab",
            "doi": "10.1000/xyz",
            "journal": "Journal X",
            "publisher": "Pub Y",
            "published": {"year": "2021"},
            "author": [{"first": "Jane", "last": "Doe", "formatted": "Doe J"}],
            "attachments": [{"filename": "allPapers//doe2021-ExamplePaper.pdf"}],
        }
    ]
    path = tmp_path / "Paperpile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    idx = load_paperpile_index(str(path))
    meta = idx["doe2021-examplepaper.pdf"]

    assert meta["title"] == "Example Paper"
    assert meta["year"] == 2021
    assert meta["citekey"] == "Doe2021-ab"
    assert meta["paperpile_id"] == "abc123"
    assert meta["authors"] == ["Doe J"]


def test_find_metadata_for_pdf_handles_special_char_variants(tmp_path: Path) -> None:
    payload = [
        {
            "_id": "x1",
            "title": "Special Name",
            "published": {"year": "2020"},
            "author": [{"formatted": "Alpha A"}],
            "attachments": [{"filename": "allPapers//García-2019—An_Example(PDF).pdf"}],
        }
    ]
    path = tmp_path / "Paperpile.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    idx = load_paperpile_index(str(path))

    # Local file variants with different punctuation/diacritics still resolve.
    meta = find_metadata_for_pdf(idx, "Garcia 2019 - An Example PDF.pdf")
    assert meta is not None
    assert meta["title"] == "Special Name"
