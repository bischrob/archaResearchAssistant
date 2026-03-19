from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "smoke_local_workflow.sh"


def test_smoke_script_help_exits_zero() -> None:
    proc = subprocess.run(
        [str(SMOKE_SCRIPT), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "Usage:" in proc.stdout


def test_smoke_script_unknown_option_exits_nonzero() -> None:
    proc = subprocess.run(
        [str(SMOKE_SCRIPT), "--not-a-real-flag"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode != 0
    assert "Unknown option:" in (proc.stdout + proc.stderr)
