from __future__ import annotations

import os
from pathlib import Path

import pytest

from rag import startup


def test_resolve_python_prefers_repo_venv_over_path_python(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    good_python = repo / ".venv" / "Scripts" / "python.exe"
    path_python = tmp_path / "bin" / "python.exe"
    good_python.parent.mkdir(parents=True, exist_ok=True)
    path_python.parent.mkdir(parents=True, exist_ok=True)
    good_python.write_text("", encoding="utf-8")
    path_python.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env.pop("PYTHON_BIN", None)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CONDA_PREFIX", None)
    monkeypatch.setattr(startup, "python_has_required_modules", lambda path: path == good_python)
    monkeypatch.setattr(startup.shutil, "which", lambda name: str(path_python) if name == "python" else None)

    result = startup.resolve_python_interpreter(repo, env=env)
    assert result == good_python


def test_resolve_python_ignores_invalid_python_bin_and_reports_failures(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    invalid_python_bin = tmp_path / "bad" / "python.exe"
    path_python = tmp_path / "bin" / "python.exe"
    invalid_python_bin.parent.mkdir(parents=True, exist_ok=True)
    path_python.parent.mkdir(parents=True, exist_ok=True)
    invalid_python_bin.write_text("", encoding="utf-8")
    path_python.write_text("", encoding="utf-8")

    env = os.environ.copy()
    env["HOME"] = str(tmp_path)
    env["PYTHON_BIN"] = str(invalid_python_bin)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CONDA_PREFIX", None)
    monkeypatch.setattr(startup, "python_has_required_modules", lambda _path: False)
    monkeypatch.setattr(startup.shutil, "which", lambda name: str(path_python) if name == "python" else None)

    with pytest.raises(startup.PythonResolutionError) as exc_info:
        startup.resolve_python_interpreter(repo, env=env)
    message = str(exc_info.value)
    assert "Could not locate a usable Python interpreter" in message
    assert str(invalid_python_bin) in message
    assert str(path_python) in message


def test_preflight_no_longer_warns_about_missing_neo4j_password_when_not_explicitly_set(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / ".env").write_text(
        "METADATA_BACKEND=zotero\n"
        "ZOTERO_DB_PATH=/tmp/zotero.sqlite\n",
        encoding="utf-8",
    )
    python_bin = tmp_path / "python.exe"
    python_bin.write_text("", encoding="utf-8")

    def fake_run(command, check=False, capture_output=True, text=True):
        exe = Path(command[0]).name.lower()
        if exe == "docker.exe" or exe == "docker":
            if command[1:] == ["compose", "version"]:
                return _Completed(returncode=0, stdout="Docker Compose version")
            if command[1:] == ["info"]:
                return _Completed(returncode=0, stdout="Server ready")
            if command[1:4] == ["inspect", "-f", "{{.State.Running}}"]:
                return _Completed(returncode=1, stdout="")
        raise AssertionError(f"Unexpected command: {command}")

    monkeypatch.setattr(startup.shutil, "which", lambda name: f"C:\\fake\\{name}.exe" if name == "docker" else None)
    monkeypatch.setattr(startup.subprocess, "run", fake_run)

    info, warnings = startup.run_preflight(repo, python_bin, port=8000)
    combined = "\n".join(info + warnings)
    assert "NEO4J_PASSWORD is missing or empty in .env" not in combined
    assert "ZOTERO_DB_PATH appears set for zotero backend" in combined


class _Completed:
    def __init__(self, returncode: int, stdout: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
