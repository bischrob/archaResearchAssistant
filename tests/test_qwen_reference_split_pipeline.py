from src.rag.qwen_structured_refs import (
    split_reference_strings_for_anystyle,
    split_reference_strings_heuristic,
)


def test_split_reference_strings_for_anystyle_prefers_heuristic_numbered_rows(monkeypatch) -> None:
    block = "[1] Smith, J. 2001. First reference.\n[2] Doe, A. 2002. Second reference."

    called = {"qwen": False}

    def _fail_qwen(*args, **kwargs):
        called["qwen"] = True
        return ["bad"]

    monkeypatch.setattr(
        "src.rag.qwen_structured_refs.split_reference_strings_with_qwen",
        _fail_qwen,
    )

    rows = split_reference_strings_for_anystyle(block)
    assert rows == [
        "Smith, J. 2001. First reference.",
        "Doe, A. 2002. Second reference.",
    ]
    assert called["qwen"] is False


def test_split_reference_strings_for_anystyle_falls_back_to_qwen_on_invalid_heuristic(monkeypatch) -> None:
    block = "References\nFigure 1\n<EOS>"

    called = {"qwen": False}

    def _fake_qwen(*args, **kwargs):
        called["qwen"] = True
        return ["Smith, J. 2001. Recovered reference."]

    monkeypatch.setattr(
        "src.rag.qwen_structured_refs.split_reference_strings_with_qwen",
        _fake_qwen,
    )

    rows = split_reference_strings_for_anystyle(block)
    assert rows == ["Smith, J. 2001. Recovered reference."]
    assert called["qwen"] is True


def test_split_reference_strings_heuristic_merges_continuation_lines() -> None:
    block = (
        "Smith, J. 2001. First line of reference\n"
        "continued second line\n"
        "Doe, A. 2002. New reference"
    )
    rows = split_reference_strings_heuristic(block)
    assert rows == [
        "Smith, J. 2001. First line of reference continued second line",
        "Doe, A. 2002. New reference",
    ]
