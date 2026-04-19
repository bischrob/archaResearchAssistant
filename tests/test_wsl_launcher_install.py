from pathlib import Path
import subprocess
import shutil
import sys


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "scripts" / "install_wsl_ra_launcher.sh"


def test_install_wsl_ra_launcher_script_uses_env_driven_repo_dir():
    content = INSTALLER.read_text(encoding="utf-8")
    assert "RA_REPO_DIR" in content
    assert 'exec "\\${RA_REPO_DIR}/scripts/run_ra_from_repo.sh"' in content


def test_install_wsl_ra_launcher_writes_repo_wrapper(tmp_path):
    if sys.platform.startswith("win"):
        return
    bash = shutil.which("bash")
    if not bash:
        return
    bin_dir = tmp_path / "bin"
    command = [bash, str(INSTALLER), str(bin_dir)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    launcher = bin_dir / "ra"
    assert launcher.exists()
    content = launcher.read_text(encoding="utf-8")
    assert "run_ra_from_repo.sh" in content
    assert 'RA_REPO_DIR="${RA_REPO_DIR:-' in content
    assert str(REPO) in content
