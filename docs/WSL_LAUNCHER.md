# WSL `ra` launcher

If you want `ra ...` to work from any WSL shell without manually activating `.venv`, install the repo-backed launcher:

```bash
/home/rjbischo/researchAssistant/scripts/install_wsl_ra_launcher.sh
```

Default install location:

- `~/.local/bin/ra`

What it does:

- keeps a tiny shell wrapper on your WSL `PATH`
- routes every call back into this repo
- reuses `scripts/resolve_python.sh` so interpreter selection matches `ra start`
- runs `python -m rag.cli` with `PYTHONPATH` pointed at `src/`

Verification:

```bash
cd /tmp
ra --json status
```

If `~/.local/bin` is not on your `PATH`, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```
