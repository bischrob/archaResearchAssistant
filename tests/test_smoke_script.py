from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke_repo_workflow.sh"
SMOKE_SCRIPT_REL = Path("scripts/smoke_repo_workflow.sh").as_posix()

pytestmark = pytest.mark.skipif(sys.platform.startswith("win"), reason="Shell smoke launcher is bash-only in CI-style tests")


def test_smoke_script_help_exits_zero() -> None:
    proc = subprocess.run(
        ["bash", SMOKE_SCRIPT_REL, "--help"],
        # bash on Windows prefers a repo-relative POSIX path here
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Usage:" in proc.stdout


def test_smoke_script_unknown_option_exits_nonzero() -> None:
    proc = subprocess.run(
        ["bash", SMOKE_SCRIPT_REL, "--not-a-real-flag"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "Unknown option:" in (proc.stdout + proc.stderr)
