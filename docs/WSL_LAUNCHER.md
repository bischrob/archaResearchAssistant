# WSL `ra` launcher

If you want `ra ...` to work from any shell without manually activating `.venv`, install the repo-backed launcher:

```bash
/home/rjbischo/researchAssistant/scripts/install_wsl_ra_launcher.sh
```

Default install location:

- `~/.local/bin/ra`

## What it does

The generated launcher:

- keeps a tiny shell wrapper on your `PATH`
- routes every call back into this repo
- reuses `scripts/run_ra_from_repo.sh` so interpreter selection matches `ra start`
- runs `python -m rag.cli` with `PYTHONPATH` pointed at `src/`
- sets a default `RA_BASE_URL` based on the environment where the launcher is installed

## Default target behavior

The generated launcher is intentionally opinionated:

- **WSL**: defaults to `http://192.168.0.37:8001` (`home2`)
- **non-WSL Linux**: defaults to `http://127.0.0.1:8001`

You can override that at runtime with either:

```bash
RA_BASE_URL=http://127.0.0.1:8001 ra status
```

or:

```bash
ra --base-url http://127.0.0.1:8001 status
```

If you reinstall the launcher after changing environments or repo behavior, rerun:

```bash
/home/rjbischo/researchAssistant/scripts/install_wsl_ra_launcher.sh
```

## Verification

From any directory:

```bash
ra --json status
```

If you want to verify a specific target explicitly:

```bash
ra --base-url http://127.0.0.1:8001 --json status
ra --base-url http://192.168.0.37:8001 --json status
```

## PATH note

If `~/.local/bin` is not on your `PATH`, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```
