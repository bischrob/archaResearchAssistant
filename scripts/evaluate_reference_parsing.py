from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rag.config import Settings
from rag.reference_parsing import detect_reference_section_from_lines, parse_reference_entries, split_references_from_lines


def main() -> int:
    fixture = ROOT / "data" / "reference_eval_cases.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    settings = Settings(citation_parser="heuristic")
    passed = 0
    for case in cases:
        lines = list(case.get("lines") or [])
        detection = detect_reference_section_from_lines(lines)
        split = split_references_from_lines(lines, section_detection=detection)
        citations, failures = parse_reference_entries(
            split.entries,
            article_id=case.get("name") or "case",
            settings=settings,
            parser_mode="heuristic",
            split_confidence=split.confidence,
        )
        start_ok = detection.start_line == case.get("expected_start_line")
        entry_ok = len(split.entries) == int(case.get("expected_entries") or 0)
        if start_ok and entry_ok:
            passed += 1
        print(
            json.dumps(
                {
                    "name": case.get("name"),
                    "detected_start_line": detection.start_line,
                    "expected_start_line": case.get("expected_start_line"),
                    "entry_count": len(split.entries),
                    "expected_entries": case.get("expected_entries"),
                    "citation_count": len(citations),
                    "failure_count": len(failures),
                    "passed": bool(start_ok and entry_ok),
                },
                ensure_ascii=False,
            )
        )
    print(json.dumps({"passed_cases": passed, "total_cases": len(cases)}, ensure_ascii=False))
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
