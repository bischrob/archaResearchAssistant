from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from .config import Settings
from .pdf_processing import Citation, normalize_title


WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.+)$")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
AUTHOR_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
QWEN_QUERY_SYSTEM_PROMPT = (
    "You rewrite user questions into compact retrieval directives for a Neo4j academic graph. "
    "Graph fields are: Author names, Article title/year, and Chunk text terms. "
    "Do NOT use boolean operators (AND/OR/NOT), parentheses, or pseudo-logic. "
    "Return exactly one line in this format: "
    "authors: <names or none> | years: <years or none> | title_terms: <terms or none> | content_terms: <terms or none>."
)
QWEN_CITATION_SYSTEM_PROMPT = (
    "You are a bibliography parser. Convert raw references to structured JSON only. "
    "Never add commentary and never drop entries."
)

_RUNTIME_LOCK = threading.Lock()
_RUNTIME_CACHE: dict[tuple[str, str, str, str, int], "_QwenRuntime"] = {}


def _strip_fences(text: str) -> str:
    out = (text or "").strip()
    out = re.sub(r"^\s*```(?:json)?\s*", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*```\s*$", "", out)
    return out.strip()


def resolve_local_model_path(path_str: str) -> Path:
    raw = (path_str or "").strip().strip('"').strip("'")
    if not raw:
        raise ValueError("Qwen path is empty.")

    candidates: list[Path] = [Path(raw).expanduser()]
    win = WINDOWS_DRIVE_RE.match(raw)
    if win:
        drive = win.group(1).lower()
        tail = win.group(2).replace("\\", "/")
        candidates.append(Path(f"/mnt/{drive}/{tail}"))
    if "\\" in raw:
        candidates.append(Path(raw.replace("\\", "/")).expanduser())

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(
        f"Qwen path not found: {raw}. "
        "If running under WSL, use /mnt/<drive>/... or keep the Windows path and ensure /mnt is mounted."
    )


def _resolve_model_and_adapter(model_path: str, adapter_path: str | None) -> tuple[Path, Path | None]:
    model = resolve_local_model_path(model_path)
    adapter = resolve_local_model_path(adapter_path) if adapter_path else None
    return model, adapter


def _extract_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1600 <= value <= 2100 else None
    text = str(value)
    match = YEAR_RE.search(text)
    return int(match.group(0)) if match else None


def _extract_doi(value: Any, fallback_text: str = "") -> str | None:
    for candidate in (value, fallback_text):
        if not candidate:
            continue
        match = DOI_RE.search(str(candidate))
        if match:
            return match.group(0).rstrip(".;,")
    return None


def _author_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    raw_values: list[str] = []
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                raw_values.append(item)
            elif isinstance(item, dict):
                family = str(item.get("family") or "").strip()
                literal = str(item.get("literal") or "").strip()
                given = str(item.get("given") or "").strip()
                candidate = family or literal or given
                if candidate:
                    raw_values.append(candidate)
    elif isinstance(value, dict):
        family = str(value.get("family") or "").strip()
        literal = str(value.get("literal") or "").strip()
        given = str(value.get("given") or "").strip()
        candidate = family or literal or given
        if candidate:
            raw_values = [candidate]

    tokens: list[str] = []
    for item in raw_values:
        parts = AUTHOR_TOKEN_RE.findall(item.lower())
        if parts:
            tokens.append(parts[-1])
    return list(dict.fromkeys(tokens))


def _decode_json_object(text: str) -> Any:
    candidates = [_strip_fences(text)]
    stripped = candidates[0]
    brace_start, brace_end = stripped.find("{"), stripped.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_start < brace_end:
        candidates.append(stripped[brace_start : brace_end + 1])
    list_start, list_end = stripped.find("["), stripped.rfind("]")
    if list_start != -1 and list_end != -1 and list_start < list_end:
        candidates.append(stripped[list_start : list_end + 1])

    for payload in candidates:
        if not payload:
            continue
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            continue
    return None


def decode_qwen_json(text: str) -> Any:
    return _decode_json_object(text)


class _QwenRuntime:
    def __init__(
        self,
        model_path: Path,
        adapter_path: Path | None,
        *,
        device: str,
        dtype: str,
        max_input_chars: int,
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.model_path = model_path
        self.adapter_path = adapter_path
        self.max_input_chars = max(500, int(max_input_chars))

        torch_dtype = None
        dtype_lower = (dtype or "auto").lower()
        if dtype_lower in {"bf16", "bfloat16"}:
            torch_dtype = torch.bfloat16
        elif dtype_lower in {"fp16", "float16", "half"}:
            torch_dtype = torch.float16
        elif dtype_lower in {"fp32", "float32"}:
            torch_dtype = torch.float32

        model_kwargs: dict[str, Any] = {"trust_remote_code": True}
        if torch_dtype is not None:
            model_kwargs["torch_dtype"] = torch_dtype

        device_lower = (device or "auto").strip().lower()
        if device_lower == "auto":
            model_kwargs["device_map"] = "auto"
        elif device_lower == "cpu":
            model_kwargs["device_map"] = {"": "cpu"}
        else:
            model_kwargs["device_map"] = {"": device}

        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
        if self.tokenizer.pad_token_id is None and self.tokenizer.eos_token is not None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(str(model_path), **model_kwargs)
        if adapter_path:
            try:
                from peft import PeftModel
            except Exception as exc:
                raise RuntimeError(
                    "peft is required to load a LoRA adapter. Install it with `pip install peft`."
                ) from exc
            model = PeftModel.from_pretrained(model, str(adapter_path), is_trainable=False)
        self.model = model.eval()

    def generate(self, messages: list[dict[str, str]], *, max_new_tokens: int, temperature: float = 0.0) -> str:
        import torch

        safe_messages: list[dict[str, str]] = []
        for msg in messages:
            role = str(msg.get("role") or "").strip() or "user"
            content = str(msg.get("content") or "").strip()
            if not content:
                continue
            safe_messages.append({"role": role, "content": content[: self.max_input_chars]})
        if not safe_messages:
            return ""

        if hasattr(self.tokenizer, "apply_chat_template"):
            rendered = self.tokenizer.apply_chat_template(
                safe_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            rendered = "\n".join(f"{m['role']}: {m['content']}" for m in safe_messages) + "\nassistant:"

        encoded = self.tokenizer(rendered, return_tensors="pt")
        first_param = next(self.model.parameters())
        target_device = first_param.device
        encoded = {k: v.to(target_device) for k, v in encoded.items()}

        do_sample = float(temperature) > 0.0
        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max(8, int(max_new_tokens)),
            "do_sample": do_sample,
            "pad_token_id": self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = max(0.01, float(temperature))

        with torch.inference_mode():
            output = self.model.generate(**encoded, **gen_kwargs)

        prompt_len = int(encoded["input_ids"].shape[1])
        completion_ids = output[0][prompt_len:]
        return self.tokenizer.decode(completion_ids, skip_special_tokens=True).strip()


def _runtime_for(model_path: str, adapter_path: str | None, settings: Settings) -> _QwenRuntime:
    resolved_model, resolved_adapter = _resolve_model_and_adapter(model_path, adapter_path)
    key = (
        str(resolved_model),
        str(resolved_adapter) if resolved_adapter else "",
        settings.qwen_device,
        settings.qwen_dtype,
        int(settings.qwen_max_input_chars),
    )
    with _RUNTIME_LOCK:
        runtime = _RUNTIME_CACHE.get(key)
        if runtime is None:
            runtime = _QwenRuntime(
                resolved_model,
                resolved_adapter,
                device=settings.qwen_device,
                dtype=settings.qwen_dtype,
                max_input_chars=settings.qwen_max_input_chars,
            )
            _RUNTIME_CACHE[key] = runtime
        return runtime


def clear_qwen_runtime_cache() -> None:
    with _RUNTIME_LOCK:
        _RUNTIME_CACHE.clear()


def generate_with_qwen(
    messages: list[dict[str, str]],
    *,
    settings: Settings | None = None,
    task: str = "citation",
    max_new_tokens: int | None = None,
    temperature: float = 0.0,
) -> str:
    cfg = settings or Settings()
    task_norm = (task or "citation").strip().lower()
    if task_norm == "query":
        model_path = cfg.qwen_query_model_path or cfg.qwen_model_path
        adapter_path = cfg.qwen_query_adapter_path or None
        token_limit = cfg.qwen_query_max_new_tokens
    else:
        model_path = cfg.qwen_citation_model_path or cfg.qwen_model_path
        adapter_path = cfg.qwen_citation_adapter_path or None
        token_limit = cfg.qwen_citation_max_new_tokens

    if not model_path:
        raise RuntimeError("QWEN3 model path is not configured. Set QWEN3_*_MODEL_PATH or QWEN3_MODEL_PATH.")

    runtime = _runtime_for(
        model_path=model_path,
        adapter_path=adapter_path,
        settings=cfg,
    )
    return runtime.generate(
        messages=messages,
        max_new_tokens=(int(max_new_tokens) if max_new_tokens is not None else int(token_limit)),
        temperature=temperature,
    )


def generate_query_directive_with_qwen(question: str, settings: Settings | None = None) -> str:
    cfg = settings or Settings()
    user = (
        f"Question:\n{(question or '').strip()}\n\n"
        "Return only the single-line directive in the required format."
    )
    return generate_with_qwen(
        messages=[
            {"role": "system", "content": QWEN_QUERY_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        settings=cfg,
        task="query",
        max_new_tokens=cfg.qwen_query_max_new_tokens,
        temperature=0.0,
    )


def _row_to_citation(
    *,
    article_id: str,
    idx: int,
    candidate: Citation,
    parsed_row: dict[str, Any] | None,
) -> Citation:
    row = parsed_row or {}
    title_guess = str(row.get("title") or row.get("title_guess") or "").strip()
    if not title_guess:
        title_guess = (candidate.title_guess or "").strip() or (candidate.raw_text or "").strip()[:180]
    year = _extract_year(row.get("year"))
    if year is None:
        year = _extract_year(row.get("date"))
    if year is None:
        year = candidate.year
    doi = _extract_doi(row.get("doi"), fallback_text=str(row.get("raw_text") or candidate.raw_text or ""))
    if doi is None:
        doi = candidate.doi
    author_tokens = _author_tokens(row.get("author_tokens"))
    if not author_tokens:
        author_tokens = _author_tokens(row.get("authors"))
    if not author_tokens:
        author_tokens = candidate.author_tokens or []
    type_guess = str(row.get("type") or row.get("type_guess") or "").strip() or candidate.type_guess

    return Citation(
        citation_id=f"{article_id}::ref::{idx}",
        raw_text=candidate.raw_text,
        year=year,
        title_guess=title_guess,
        normalized_title=normalize_title(title_guess),
        doi=doi,
        source="qwen_lora",
        type_guess=type_guess,
        author_tokens=author_tokens,
    )


def _parse_citation_rows(text: str) -> list[dict[str, Any]]:
    payload = _decode_json_object(text)
    if payload is None:
        return []
    if isinstance(payload, dict):
        rows = payload.get("citations")
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def extract_citations_with_qwen(
    article_id: str,
    citation_candidates: list[Citation],
    *,
    settings: Settings | None = None,
) -> list[Citation]:
    if not citation_candidates:
        return []
    cfg = settings or Settings()
    model_path = cfg.qwen_citation_model_path or cfg.qwen_model_path
    if not model_path:
        raise RuntimeError("QWEN3 model path is not configured. Set QWEN3_CITATION_MODEL_PATH or QWEN3_MODEL_PATH.")

    runtime = _runtime_for(
        model_path=model_path,
        adapter_path=(cfg.qwen_citation_adapter_path or None),
        settings=cfg,
    )
    batch_size = max(1, min(int(cfg.qwen_citation_batch_size), 64))
    out: list[Citation] = []

    for start in range(0, len(citation_candidates), batch_size):
        batch = citation_candidates[start : start + batch_size]
        payload = [{"id": idx, "raw_text": c.raw_text} for idx, c in enumerate(batch)]
        user = (
            "Parse each reference below and return JSON only.\n"
            "Use exactly this schema:\n"
            '{"citations":[{"id":0,"title":"","year":null,"doi":null,"author_tokens":[],"type":null}]}\n'
            "Keep one output citation for each input id.\n"
            f"Input references JSON:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        raw = runtime.generate(
            messages=[
                {"role": "system", "content": QWEN_CITATION_SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            max_new_tokens=cfg.qwen_citation_max_new_tokens,
            temperature=0.0,
        )
        parsed_rows = _parse_citation_rows(raw)
        by_id: dict[int, dict[str, Any]] = {}
        for row in parsed_rows:
            row_id = row.get("id")
            if isinstance(row_id, int):
                by_id[row_id] = row
                continue
            if isinstance(row_id, str):
                stripped = row_id.strip()
                if stripped.isdigit():
                    by_id[int(stripped)] = row

        for local_idx, candidate in enumerate(batch):
            global_idx = start + local_idx
            parsed = by_id.get(local_idx)
            out.append(
                _row_to_citation(
                    article_id=article_id,
                    idx=global_idx,
                    candidate=candidate,
                    parsed_row=parsed,
                )
            )

    return out
