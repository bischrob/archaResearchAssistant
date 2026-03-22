from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any

from .config import Settings


def _command_for_task(task: str, settings: Settings | None = None) -> str:
    cfg = settings or Settings()
    specific = {
        "query_preprocess": cfg.openclaw_agent_preprocess_cmd,
        "grounded_answer": cfg.openclaw_agent_answer_cmd,
    }.get(task, "")
    return (specific or cfg.openclaw_agent_command or "").strip()


def invoke_openclaw_agent(task: str, payload: dict[str, Any], *, settings: Settings | None = None, timeout: int = 120) -> dict[str, Any] | None:
    command = _command_for_task(task, settings=settings)
    if not command:
        return None
    env = os.environ.copy()
    env["OPENCLAW_AGENT_TASK"] = task
    proc = subprocess.run(
        shlex.split(command),
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"OpenClaw agent command failed with code {proc.returncode}").strip())
    body = (proc.stdout or '').strip()
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return {"text": body}
    return parsed if isinstance(parsed, dict) else {"data": parsed}
