#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


def _load_repo_env() -> None:
    env_path = Path(__file__).resolve().parent.parent / '.env'
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_repo_env()


def _resolve_openclaw_bin() -> str:
    configured = (os.getenv("OPENCLAW_BIN") or "").strip()
    if configured:
        return configured
    found = shutil.which("openclaw")
    if found:
        return found
    fallback = Path("/mnt/c/Users/rjbischo/AppData/Roaming/npm/openclaw")
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("OpenClaw CLI not found. Set OPENCLAW_BIN or install openclaw.")


def _parse_node_major(version_text: str) -> int | None:
    match = re.search(r"v?(\d+)", version_text or "")
    return int(match.group(1)) if match else None


def _node_major(node_bin: str) -> int | None:
    try:
        proc = subprocess.run([node_bin, "-v"], capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return _parse_node_major((proc.stdout or proc.stderr or "").strip())


def _resolve_node_bin(min_major: int = 22) -> str | None:
    configured = (os.getenv("OPENCLAW_NODE_BIN") or "").strip()
    candidates: list[str] = []
    if configured:
        candidates.append(configured)

    current = shutil.which("node")
    if current:
        candidates.append(current)

    nvm_dir = Path(os.getenv("NVM_DIR") or Path.home() / ".nvm")
    versions_dir = nvm_dir / "versions" / "node"
    if versions_dir.exists():
        for child in sorted(versions_dir.iterdir(), reverse=True):
            candidate = child / "bin" / "node"
            if candidate.exists():
                candidates.append(str(candidate))

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        major = _node_major(candidate)
        if major is not None and major >= min_major:
            return candidate
    return None


def _build_openclaw_command() -> list[str]:
    openclaw_bin = _resolve_openclaw_bin()
    node_bin = _resolve_node_bin()
    script_path = Path(openclaw_bin).resolve().parent / "node_modules" / "openclaw" / "openclaw.mjs"
    if node_bin and script_path.exists():
        return [node_bin, str(script_path)]
    return [openclaw_bin]


def _read_payload() -> dict:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise RuntimeError("OpenClaw adapter expected a JSON object payload.")
    return data


def _build_prompt(task: str, payload: dict) -> str:
    if task == "query_preprocess":
        question = str(payload.get("question") or "").strip()
        return (
            "Rewrite the following question into exactly one line using this schema:\n"
            "authors: ... | years: ... | title_terms: ... | content_terms: ...\n"
            "Use 'none' for empty fields. Do not add explanation.\n\n"
            f"Question: {question}"
        )
    if task == "grounded_answer":
        question = str(payload.get("question") or "").strip()
        fallback = payload.get("fallback") or {}
        context = str(fallback.get("context") or "").strip()
        return (
            "You are given retrieved RAG results that may contain noisy or irrelevant items.\n"
            "First evaluate each citation for direct relevance to the question.\n"
            "Then answer using only citations you judged relevant enough.\n"
            "Do not summarize irrelevant, weakly related, or off-topic results.\n"
            "If none of the retrieved evidence is relevant enough, say that explicitly and do not cite irrelevant items.\n"
            "Return JSON only with keys:\n"
            "- answer: string\n"
            "- relevant_citation_ids: array of citation ids you judged relevant enough to use\n"
            "- excluded_citation_ids: array of citation ids judged not relevant enough\n"
            "- relevance_summary: short sentence describing the filtering outcome\n"
            "- synthesis_status: one of succeeded, irrelevant_context, insufficient_context\n"
            "Rules:\n"
            "- Every factual claim in answer must include one or more inline citations like [C1].\n"
            "- The answer may only cite ids listed in relevant_citation_ids.\n"
            "- If relevant_citation_ids is empty, answer should explicitly say the retrieved evidence is not relevant enough.\n"
            "- Do not invent citations or facts.\n\n"
            f"Question: {question}\n\n"
            f"Retrieved context:\n{context}"
        )
    if task == "reference_split":
        reference_block = str(payload.get("reference_block") or "").strip()
        return (
            "Split this bibliography block into one reference per line.\n"
            "Return JSON only with a top-level 'references' array of strings.\n"
            "Preserve order, keep each reference on one line, and do not include commentary.\n\n"
            f"Bibliography block:\n{reference_block}"
        )
    if task == "reference_tail_trim":
        suspicious_start_line = payload.get("suspicious_start_line")
        tail_lines = payload.get("tail_lines") or []
        rendered = []
        for row in tail_lines:
            if not isinstance(row, dict):
                continue
            rendered.append(f"{row.get('line_idx')}: {str(row.get('text') or '').strip()}")
        return (
            "You are deciding where a bibliography ends and appendix or other spillover begins.\n"
            "Return JSON only with keys 'last_reference_line' and optional 'reason'.\n"
            "Choose the last numbered line that still belongs to the bibliography.\n"
            "If spillover begins immediately, return the last real reference line before it.\n"
            f"The heuristics already suspect spillover begins near line {suspicious_start_line}.\n\n"
            "Tail lines:\n" + "\n".join(rendered)
        )
    raise RuntimeError(f"Unsupported OpenClaw task: {task}")


def _extract_text(stdout: str) -> str:
    text = (stdout or "").strip()
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    for line in reversed(lines):
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                value = parsed.get("answer") or parsed.get("directive") or parsed.get("text")
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return lines[-1]


def _responses_api_text(payload: dict) -> str:
    output = payload.get("output") or []
    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
    if chunks:
        return "\n".join(chunks).strip()
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    raise RuntimeError("Responses API returned no text output.")


def _invoke_openai_responses(*, task: str, prompt: str, timeout: int) -> str:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured for bounded fallback synthesis.")
    model = (os.getenv("OPENAI_MODEL") or "gpt-5.1").strip()
    system_prompt = {
        "query_preprocess": "Return only the requested directive line. No markdown, no explanation.",
        "grounded_answer": (
            "Return JSON only. Evaluate retrieval relevance before answering. Use only relevant citations. "
            "If nothing retrieved is relevant enough, say so explicitly and leave relevant_citation_ids empty."
        ),
        "reference_split": "Return valid JSON only.",
        "reference_tail_trim": "Return valid JSON only.",
    }.get(task, "Return only the requested output.")
    body = {
        "model": model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": prompt}]},
        ],
    }
    req = urllib_request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI fallback HTTP {exc.code}: {detail[:500].strip()}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI fallback failed: {exc}") from exc
    return _responses_api_text(payload)


def _should_try_openclaw_for_task(task: str) -> bool:
    if task != "grounded_answer":
        return True
    raw = (os.getenv("OPENCLAW_GROUNDED_ANSWER_MODE") or "fallback").strip().lower()
    return raw in {"agent", "openclaw", "prefer-agent"}


def _invoke_openclaw_agent_once(*, task: str, prompt: str, timeout: int) -> str:
    command = [
        *_build_openclaw_command(),
        "agent",
        "--json",
        "--agent",
        "default",
        "--message",
        prompt,
        "--timeout",
        str(timeout),
        "--no-deliver",
    ]
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout + 10,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or f"OpenClaw exited with code {proc.returncode}").strip())
    text = _extract_text(proc.stdout)
    if text:
        return text
    try:
        parsed = json.loads((proc.stdout or "").strip())
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenClaw returned no extractable answer text.") from exc
    payloads = parsed.get("payloads") if isinstance(parsed, dict) else None
    if isinstance(payloads, list):
        texts = [str(item.get("text") or "").strip() for item in payloads if isinstance(item, dict)]
        joined = "\n".join(x for x in texts if x)
        if joined.strip():
            return joined.strip()
    raise RuntimeError("OpenClaw returned no extractable answer text.")


def _run_task(task: str, payload: dict) -> str:
    prompt = _build_prompt(task, payload)
    timeout = int(os.getenv("OPENCLAW_ADAPTER_TIMEOUT", "120"))
    errors: list[str] = []

    if _should_try_openclaw_for_task(task):
        try:
            return _invoke_openclaw_agent_once(task=task, prompt=prompt, timeout=timeout)
        except Exception as exc:
            errors.append(f"openclaw: {exc}")
            if task != "grounded_answer":
                raise RuntimeError(errors[-1]) from exc

    if task == "grounded_answer":
        try:
            fallback_timeout = int(os.getenv("OPENCLAW_FALLBACK_TIMEOUT", str(min(timeout, 90))))
            return _invoke_openai_responses(task=task, prompt=prompt, timeout=fallback_timeout)
        except Exception as exc:
            errors.append(f"openai_fallback: {exc}")

    if errors:
        raise RuntimeError("; ".join(errors))
    raise RuntimeError(f"No execution path available for task: {task}")


def main() -> int:
    task = (os.getenv("OPENCLAW_AGENT_TASK") or "").strip()
    if not task:
        raise RuntimeError("OPENCLAW_AGENT_TASK is not set.")
    payload = _read_payload()
    text = _run_task(task, payload)
    if task == "query_preprocess":
        json.dump({"directive": text}, sys.stdout, ensure_ascii=False)
    elif task in {"reference_split", "reference_tail_trim"}:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"text": text}
        json.dump(parsed, sys.stdout, ensure_ascii=False)
    elif task == "grounded_answer":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = {"answer": text}
        if not isinstance(parsed, dict):
            parsed = {"answer": str(parsed)}
        json.dump(parsed, sys.stdout, ensure_ascii=False)
    else:
        json.dump({"answer": text}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        json.dump({"error": str(exc)}, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        raise
