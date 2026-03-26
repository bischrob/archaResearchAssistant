from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def test_resolve_python_prefers_repo_venv_over_path_python(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")

    good_python = repo / ".venv/bin/python"
    path_python = tmp_path / "bin/python"

    _make_executable(good_python, "#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n")
    _make_executable(path_python, "#!/usr/bin/env bash\ncat >/dev/null\nexit 0\n")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.pop("PYTHON_BIN", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CONDA_PREFIX", None)
    env["PATH"] = f"{path_python.parent}:{env['PATH']}"

    result = subprocess.run(
        [str(repo / "scripts/resolve_python.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(good_python)


def test_resolve_python_ignores_invalid_python_bin_and_reports_failures(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", repo / "scripts")

    invalid_python_bin = tmp_path / "bad/python"
    path_python = tmp_path / "bin/python"

    _make_executable(invalid_python_bin, "#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n")
    _make_executable(path_python, "#!/usr/bin/env bash\ncat >/dev/null\nexit 1\n")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHON_BIN"] = str(invalid_python_bin)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CONDA_PREFIX", None)
    env["PATH"] = f"{path_python.parent}:{env['PATH']}"

    result = subprocess.run(
        [str(repo / "scripts/resolve_python.sh")],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 1
    assert "Could not locate a usable Python interpreter" in result.stderr
    assert str(invalid_python_bin) in result.stderr
    assert str(path_python) in result.stderr


def test_preflight_no_longer_warns_about_missing_neo4j_password_when_not_explicitly_set(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts_dir = repo / "scripts"
    scripts_dir.mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts/preflight_check.sh", scripts_dir / "preflight_check.sh")
    shutil.copy2(REPO_ROOT / "scripts/resolve_python.sh", scripts_dir / "resolve_python.sh")
    (repo / ".env").write_text(
        "METADATA_BACKEND=zotero\n"
        "ZOTERO_DB_PATH=/tmp/zotero.sqlite\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    docker_script = fake_bin / "docker"
    _make_executable(
        docker_script,
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == \"compose\" && \"$2\" == \"version\" ]]; then exit 0; fi\n"
        "if [[ \"$1\" == \"info\" ]]; then exit 0; fi\n"
        "if [[ \"$1\" == \"inspect\" ]]; then exit 1; fi\n"
        "exit 0\n",
    )

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["PYTHON_BIN"] = shutil.which("python3") or shutil.which("python") or env.get("PYTHON_BIN", "")

    result = subprocess.run(
        [str(scripts_dir / "preflight_check.sh")],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    combined = f"{result.stdout}\n{result.stderr}"
    assert "NEO4J_PASSWORD is missing or empty in .env" not in combined
    assert "ZOTERO_DB_PATH appears set for zotero backend" in combined
