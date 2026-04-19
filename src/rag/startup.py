from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse


REQUIRED_MODULES = ("fastapi", "uvicorn", "neo4j", "sentence_transformers")
DEFAULT_CONDA_ENV_NAMES = ("researchassistant", "researchAssistant", "researchassistant311")


class PythonResolutionError(RuntimeError):
    def __init__(self, checked: list[str]) -> None:
        self.checked = checked
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        lines = [
            "Could not locate a usable Python interpreter with required modules "
            f"({', '.join(REQUIRED_MODULES)}).",
            "Checked candidates in priority order:",
        ]
        lines.extend(f"  - {candidate}" for candidate in self.checked)
        lines.append(
            "Hint: create the repo environment and install dependencies, e.g. "
            "python -m pip install -e . && python -m pip install -r requirements.txt"
        )
        return "\n".join(lines)


def _python_candidates_for_prefix(prefix: Path | None) -> list[Path]:
    if prefix is None:
        return []
    return [
        prefix / "bin" / "python",
        prefix / "Scripts" / "python.exe",
        prefix / "python.exe",
        prefix / "python",
    ]


def _conda_base_from_exe(conda_exe: str) -> Path | None:
    raw = Path(conda_exe)
    if raw.name.lower().startswith("conda"):
        scripts_dir = raw.parent
        if scripts_dir.name.lower() == "scripts":
            return scripts_dir.parent
        return scripts_dir
    return None


def _conda_bases(env: dict[str, str] | None = None) -> list[Path]:
    env = env or os.environ
    bases: list[Path] = []

    conda_exe = env.get("CONDA_EXE", "").strip()
    if conda_exe:
        maybe = _conda_base_from_exe(conda_exe)
        if maybe is not None:
            bases.append(maybe)
    elif shutil.which("conda"):
        proc = subprocess.run(
            ["conda", "info", "--base"],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            bases.append(Path(proc.stdout.strip()))

    home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    for common_base in (home / "miniconda3", home / "anaconda3", Path("/opt/conda")):
        if common_base.exists():
            bases.append(common_base)

    unique: list[Path] = []
    seen: set[str] = set()
    for base in bases:
        key = str(base)
        if key not in seen:
            seen.add(key)
            unique.append(base)
    return unique


def iter_python_candidates(
    repo_root: Path,
    *,
    env: dict[str, str] | None = None,
    conda_env_names: tuple[str, ...] = DEFAULT_CONDA_ENV_NAMES,
) -> list[Path]:
    env = env or os.environ
    candidates: list[Path] = []

    def append(candidate: Path | None) -> None:
        if candidate is None:
            return
        if not candidate.exists():
            return
        if str(candidate) not in {str(item) for item in candidates}:
            candidates.append(candidate)

    explicit = env.get("PYTHON_BIN", "").strip()
    append(Path(explicit) if explicit else None)

    for candidate in _python_candidates_for_prefix(repo_root / ".venv"):
        append(candidate)

    virtual_env = env.get("VIRTUAL_ENV", "").strip()
    if virtual_env:
        for candidate in _python_candidates_for_prefix(Path(virtual_env)):
            append(candidate)

    conda_prefix = env.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        for candidate in _python_candidates_for_prefix(Path(conda_prefix)):
            append(candidate)

    for conda_base in _conda_bases(env):
        for env_name in conda_env_names:
            for candidate in _python_candidates_for_prefix(conda_base / "envs" / env_name):
                append(candidate)

    for name in ("python3", "python", "py"):
        resolved = shutil.which(name)
        if not resolved:
            continue
        candidate = Path(resolved)
        if name == "py":
            append(candidate)
            continue
        append(candidate)

    return candidates


def python_has_required_modules(python_bin: Path) -> bool:
    if python_bin.name.lower() == "py.exe" or python_bin.name.lower() == "py":
        command = [str(python_bin), "-3", "-c"]
    else:
        command = [str(python_bin), "-c"]
    probe = (
        "import importlib.util, sys; "
        f"required={REQUIRED_MODULES!r}; "
        "missing=[name for name in required if importlib.util.find_spec(name) is None]; "
        "sys.exit(0 if not missing else 1)"
    )
    proc = subprocess.run(
        [*command, probe],
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def resolve_python_interpreter(
    repo_root: Path,
    *,
    env: dict[str, str] | None = None,
) -> Path:
    candidates = iter_python_candidates(repo_root, env=env)
    checked: list[str] = []
    for candidate in candidates:
        checked.append(str(candidate))
        if python_has_required_modules(candidate):
            return candidate
    raise PythonResolutionError(checked)


def _read_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not env_path.exists():
        return values
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _docker_command() -> list[str] | None:
    docker = shutil.which("docker")
    if not docker:
        return None
    compose = subprocess.run(
        [docker, "compose", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if compose.returncode == 0:
        return [docker, "compose"]
    docker_compose = shutil.which("docker-compose")
    if docker_compose:
        return [docker_compose]
    return None


def docker_command() -> str:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("Missing required command: docker")
    return docker


def docker_compose_command() -> list[str]:
    compose_cmd = _docker_command()
    if compose_cmd is None:
        raise RuntimeError("Neither 'docker compose' nor 'docker-compose' is available")
    return compose_cmd


def run_preflight(repo_root: Path, python_bin: Path, port: int) -> tuple[list[str], list[str]]:
    info: list[str] = [f"Using python: {python_bin}"]
    warnings: list[str] = []

    docker = docker_command()
    info.append(f"Found command: {docker}")

    compose_cmd = docker_compose_command()
    info.append(f"Docker compose available via: {' '.join(compose_cmd)}")

    docker_info = subprocess.run(
        [docker, "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    if docker_info.returncode != 0:
        raise RuntimeError("Docker daemon is not reachable. Start Docker and retry.")
    info.append("Docker daemon reachable")

    env_path = repo_root / ".env"
    env_values = _read_env_file(env_path)
    if env_path.exists():
        info.append("Found .env")
    else:
        warnings.append(".env not found. Copy .env.example to .env and set values.")

    backend = env_values.get("METADATA_BACKEND", "").strip().lower()
    if not backend:
        warnings.append("METADATA_BACKEND is not set in .env (expected 'zotero' or 'paperpile').")
    elif backend == "zotero":
        if env_values.get("ZOTERO_DB_PATH", "").strip():
            info.append("ZOTERO_DB_PATH appears set for zotero backend")
        else:
            warnings.append("METADATA_BACKEND=zotero but ZOTERO_DB_PATH is missing/empty.")
    elif backend == "paperpile":
        if env_values.get("PAPERPILE_JSON", "").strip():
            info.append("PAPERPILE_JSON appears set for paperpile backend")
        else:
            warnings.append("METADATA_BACKEND=paperpile but PAPERPILE_JSON is missing/empty.")
    else:
        warnings.append(f"METADATA_BACKEND='{backend}' is not recognized (expected zotero or paperpile).")

    for key in ("ZOTERO_DB_PATH", "ZOTERO_STORAGE_ROOT", "PDF_SOURCE_DIR", "PAPERPILE_JSON"):
        raw = env_values.get(key, "").strip()
        if not raw:
            continue
        path = Path(raw)
        if path.exists():
            info.append(f"{key} exists: {raw}")
            if path.is_dir() and os.access(path, os.W_OK):
                info.append(f"{key} is writable: {raw}")
            elif path.is_dir():
                warnings.append(f"{key} exists but is not writable: {raw}")
        else:
            warnings.append(f"{key} is set but does not exist on this host: {raw}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            warnings.append(f"Port {port} is in use. start.sh will auto-select the next open port.")
        else:
            info.append(f"Port {port} is free")

    neo4j_running = subprocess.run(
        [docker, "inspect", "-f", "{{.State.Running}}", "neo4j"],
        check=False,
        capture_output=True,
        text=True,
    )
    if neo4j_running.returncode == 0 and neo4j_running.stdout.strip() == "true":
        info.append("Neo4j container is running")
    else:
        warnings.append("Neo4j container not running (this is fine before first start).")

    return info, warnings


def ensure_docker_daemon(docker: str | None = None) -> None:
    docker = docker or docker_command()
    docker_info = subprocess.run(
        [docker, "info"],
        check=False,
        capture_output=True,
        text=True,
    )
    if docker_info.returncode != 0:
        raise RuntimeError("Docker daemon is not reachable. Start Docker and retry.")


def is_port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def pick_open_port(start_port: int) -> int:
    port = start_port
    while port <= 65535:
        if is_port_free(port):
            return port
        port += 1
    raise RuntimeError(f"Could not find an open port between {start_port} and 65535.")


def ensure_neo4j_running(compose_cmd: list[str], docker: str | None = None) -> str:
    docker = docker or docker_command()
    running = subprocess.run(
        [docker, "inspect", "-f", "{{.State.Running}}", "neo4j"],
        check=False,
        capture_output=True,
        text=True,
    )
    if running.returncode == 0 and running.stdout.strip() == "true":
        return "already-running"

    started = subprocess.run(
        [*compose_cmd, "up", "-d", "neo4j"],
        check=False,
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        detail = (started.stderr or started.stdout or "").strip()
        raise RuntimeError(f"Failed to start Neo4j container: {detail or 'unknown docker compose error'}")
    return "started"


def initialize_neo4j_schema(
    repo_root: Path,
    python_bin: Path,
    *,
    wait_seconds: int,
    retry_interval: int,
) -> None:
    command = [
        str(python_bin),
        str(repo_root / "scripts" / "init_neo4j_indexes.py"),
        "--wait-seconds",
        str(wait_seconds),
        "--retry-interval",
        str(retry_interval),
    ]
    proc = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Neo4j schema initialization failed: {detail or 'unknown error'}")


def default_port_from_base_url(base_url: str, fallback: int = 8001) -> int:
    parsed = urlparse(base_url)
    if parsed.port is not None:
        return parsed.port
    if parsed.scheme == "https":
        return 443
    if parsed.scheme == "http":
        return 80
    return fallback


def prepare_runtime_env(repo_root: Path, python_bin: Path, base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    env["PYTHON_BIN"] = str(python_bin)
    env["PATH"] = f"{python_bin.parent}{os.pathsep}{env.get('PATH', '')}" if env.get("PATH") else str(python_bin.parent)

    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    if existing_pythonpath:
        parts = existing_pythonpath.split(os.pathsep)
        if src_path not in parts:
            env["PYTHONPATH"] = os.pathsep.join([src_path, *parts])
    else:
        env["PYTHONPATH"] = src_path
    return env


def build_uvicorn_command(
    python_bin: Path,
    *,
    host: str,
    port: int,
    reload_enabled: bool = False,
) -> list[str]:
    command = [str(python_bin), "-m", "uvicorn", "webapp.main:app", "--host", host, "--port", str(port)]
    if reload_enabled:
        command.append("--reload")
    return command


def local_health_base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def current_python_has_required_modules() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_MODULES)


def repo_root_from(path: Path) -> Path:
    return path.resolve().parents[2]
