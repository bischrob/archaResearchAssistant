from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

from src.rag.qwen_structured_refs import _sanitize_reference_rows, _split_numbered_rows


def _load_prepare_module():
    root = Path(__file__).resolve().parents[1]
    module_path = root / "scripts" / "prepare_qwen_reference_curriculum.py"
    spec = importlib.util.spec_from_file_location("prepare_qwen_reference_curriculum", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_sanitize_reference_rows_splits_merged_and_drops_noise() -> None:
    rows = [
        "[1] Alpha Author. First ref. 2016. [2] Beta Author. Second ref. 2017.",
        "Attention Visualizations Figure 3",
        "<EOS> <pad>",
    ]
    cleaned = _sanitize_reference_rows(rows)
    assert len(cleaned) == 2
    assert cleaned[0].startswith("Alpha Author.")
    assert cleaned[1].startswith("Beta Author.")


def test_split_numbered_rows_extracts_numbered_items() -> None:
    block = (
        "References\n"
        "[1] Alpha Author. First ref. 2016.\n"
        "[2] Beta Author. Second ref. 2017.\n"
        "Figure 3: Not a reference."
    )
    rows = _sanitize_reference_rows(_split_numbered_rows(block))
    assert len(rows) == 2
    assert all("Figure 3" not in row for row in rows)


def test_curriculum_canonical_reference_list_removes_markers_and_noise() -> None:
    prep = _load_prepare_module()
    refs = prep._canonical_reference_list(
        [
            "[1] Alpha Author. First ref. 2016.",
            "2. Beta Author. Second ref. 2017.",
            "References",
            "<EOS>",
        ]
    )
    assert refs == [
        "Alpha Author. First ref. 2016.",
        "Beta Author. Second ref. 2017.",
    ]


def test_synthesize_split_examples_from_parse_examples() -> None:
    prep = _load_prepare_module()
    examples = [
        prep.CurriculumExample(
            tier="silver",
            task="parse_reference_json",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Raw reference: [1] Alpha Author. First ref. 2016."},
                {"role": "assistant", "content": '{"title":"First ref"}'},
            ],
            meta={"task": "parse_reference_json"},
        ),
        prep.CurriculumExample(
            tier="silver",
            task="parse_reference_json",
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "Raw reference: [2] Beta Author. Second ref. 2017."},
                {"role": "assistant", "content": '{"title":"Second ref"}'},
            ],
            meta={"task": "parse_reference_json"},
        ),
    ]
    out, stats = prep.synthesize_split_examples_from_parse_examples(
        examples=examples,
        tier="silver",
        source="silver_parse_pool",
        seed=7,
        max_examples=10,
        window_size=8,
        window_step=4,
        noise_prob=0.0,
    )
    assert stats["generated"] >= 1
    assert out
    payload = out[0].messages[2]["content"]
    assert '"references"' in payload
    assert "[1]" not in payload
