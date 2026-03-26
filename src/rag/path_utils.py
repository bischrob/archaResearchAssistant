from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


UNC_RE = re.compile(r"^\\\\([^\\]+)\\([^\\]+)(?:\\(.*))?$")
WIN_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/].*")


def is_wsl() -> bool:
    if os.getenv("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text(encoding="utf-8", errors="ignore").lower()
    except Exception:
        return False


def _unc_parts(raw: str) -> tuple[str, str, str] | None:
    m = UNC_RE.match((raw or "").strip())
    if not m:
        return None
    host = m.group(1).strip()
    share = m.group(2).strip()
    rest = (m.group(3) or "").strip("\\")
    return host, share, rest


def _wslpath_unc(raw: str) -> Path | None:
    try:
        proc = subprocess.run(
            ["wslpath", "-u", raw],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    return Path(out)


def _wslpath_any(raw: str) -> Path | None:
    try:
        proc = subprocess.run(
            ["wslpath", "-u", raw],
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return None
    return Path(out)


def _drvfs_mount_unc(raw: str) -> Path | None:
    parts = _unc_parts(raw)
    if not parts:
        return None
    host, share, rest = parts
    mount_root = Path("/mnt") / share.lower()
    try:
        mount_root.mkdir(parents=True, exist_ok=True)
    except Exception:
        return None

    unc_share = f"\\\\{host}\\{share}"
    mounted = False
    for cmd in (
        ["mount", "-t", "drvfs", unc_share, str(mount_root)],
        ["sudo", "-n", "mount", "-t", "drvfs", unc_share, str(mount_root)],
    ):
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                mounted = True
                break
        except Exception:
            continue
    if not mounted:
        # Some WSL installs auto-expose UNC under /mnt/wsl/UNC even if explicit mount fails.
        pass

    return mount_root / Path(rest.replace("\\", "/")) if rest else mount_root


def resolve_input_path(raw: str) -> Path:
    text = (raw or "").strip()
    if not text:
        return Path(text)
    if not is_wsl():
        return Path(text)
    if WIN_DRIVE_RE.match(text):
        p = _wslpath_any(text)
        return p if p is not None else Path(text)
    if not text.startswith("\\\\"):
        return Path(text)

    p = _wslpath_unc(text)
    if p is not None:
        return p

    mounted = _drvfs_mount_unc(text)
    if mounted is not None:
        return mounted
    return Path(text)
