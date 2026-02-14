import json
from pathlib import Path

from src.rag.paperpile_metadata import load_paperpile_index


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

