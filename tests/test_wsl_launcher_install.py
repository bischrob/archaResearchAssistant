from pathlib import Path
import subprocess


REPO = Path("/home/rjbischo/researchAssistant")
INSTALLER = REPO / "scripts" / "install_wsl_ra_launcher.sh"


def test_install_wsl_ra_launcher_writes_repo_wrapper(tmp_path):
    bin_dir = tmp_path / "bin"
    result = subprocess.run([str(INSTALLER), str(bin_dir)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr

    launcher = bin_dir / "ra"
    assert launcher.exists()
    content = launcher.read_text(encoding="utf-8")
    assert "run_ra_from_repo.sh" in content
    assert str(REPO / "scripts" / "run_ra_from_repo.sh") in content
