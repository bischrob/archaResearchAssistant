#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PARSE_SYSTEM_PROMPT = (
    "You are a bibliography parser. Convert each raw reference string into compact JSON with fields: "
    "title, year, doi, author_tokens, and type."
)
SPLIT_SYSTEM_PROMPT = (
    "You split bibliography text into individual references. "
    'Return JSON only with this schema: {"references":["<one reference>", "<one reference>"]}. '
    "Do not add commentary and do not invent text."
)
DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(1[6-9]\d{2}|20\d{2}|2100)\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]+")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@dataclass
class CurriculumExample:
    tier: str
    task: str
    messages: list[dict[str, str]]
    meta: dict[str, Any]

    def to_row(self) -> dict[str, Any]:
        return {"messages": self.messages, "meta": self.meta}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build staged Qwen3 LoRA curriculum datasets for reference split/parse.")
    p.add_argument(
        "--silver-jsonl",
        action="append",
        default=[],
        help="Silver JSONL files in chat/messages format (repeatable).",
    )
    p.add_argument(
        "--synthetic-jsonl",
        action="append",
        default=[],
        help="Synthetic JSONL files in chat/messages format (repeatable).",
    )
    p.add_argument(
        "--gold-articles-json",
        default="data/reference_lora_gold_articles.json",
        help="Gold article supervision JSON file.",
    )
    p.add_argument(
        "--output-dir",
        default="data/reference_lora_curriculum",
        help="Directory for staged curriculum outputs.",
    )
    p.add_argument("--eval-ratio", type=float, default=0.15)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-raw-chars", type=int, default=1200)
    p.add_argument("--min-title-chars", type=int, default=5)
    p.add_argument("--stage1-weights", default="synthetic=6,silver=3,gold=1")
    p.add_argument("--stage2-weights", default="gold=6,silver=3,synthetic=1")
    p.add_argument("--stage1-max-train", type=int, default=0, help="0 means no cap.")
    p.add_argument("--stage2-max-train", type=int, default=0, help="0 means no cap.")
    return p.parse_args()


def _normalize_ws(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _extract_raw_reference(user_text: str) -> str:
    if "Raw reference:" in user_text:
        raw = user_text.split("Raw reference:", 1)[1]
    else:
        raw = user_text
    return _normalize_ws(raw)


def _safe_year(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1600 <= value <= 2100 else None
    m = YEAR_RE.search(str(value))
    return int(m.group(0)) if m else None


def _safe_doi(value: Any, fallback: str = "") -> str | None:
    for candidate in (value, fallback):
        if not candidate:
            continue
        m = DOI_RE.search(str(candidate))
        if m:
            return m.group(0).rstrip(".;,")
    return None


def _person_token(person: Any) -> str | None:
    if isinstance(person, str):
        parts = WORD_RE.findall(person.lower())
        return parts[-1] if parts else None
    if isinstance(person, dict):
        raw = str(person.get("family") or person.get("literal") or person.get("given") or "").strip()
        parts = WORD_RE.findall(raw.lower())
        return parts[-1] if parts else None
    return None


def _safe_author_tokens(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, list):
        for item in value:
            token = _person_token(item)
            if token:
                out.append(token)
    elif value is not None:
        token = _person_token(value)
        if token:
            out.append(token)
    dedup: list[str] = []
    seen: set[str] = set()
    for item in out:
        if item in seen:
            continue
        seen.add(item)
        dedup.append(item)
    return dedup[:6]


def _canonical_parse_target(obj: Any, raw_reference: str = "") -> dict[str, Any] | None:
    if not isinstance(obj, dict):
        return None
    title = _normalize_ws(str(obj.get("title") or ""))
    if not title:
        return None
    year = _safe_year(obj.get("year"))
    doi = _safe_doi(obj.get("doi"), raw_reference)
    author_tokens = _safe_author_tokens(obj.get("author_tokens"))
    type_guess = obj.get("type")
    if type_guess is not None:
        type_guess = _normalize_ws(str(type_guess)) or None
    return {
        "title": title,
        "year": year,
        "doi": doi,
        "author_tokens": author_tokens,
        "type": type_guess,
    }


def _parse_weight_map(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for part in (text or "").split(","):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        k = key.strip().lower()
        try:
            v = int(value.strip())
        except Exception:
            continue
        if k and v > 0:
            out[k] = v
    return out


def _example_key(ex: CurriculumExample) -> str:
    user_text = ""
    assistant_text = ""
    if len(ex.messages) >= 2:
        user_text = _normalize_ws(ex.messages[1].get("content") or "")
    if len(ex.messages) >= 3:
        assistant_text = _normalize_ws(ex.messages[2].get("content") or "")
    payload = f"{ex.task}|{user_text}|{assistant_text}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            text = line.strip()
            if not text:
                continue
            try:
                row = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _extract_messages(row: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    messages = row.get("messages")
    if not isinstance(messages, list):
        return out
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = _normalize_ws(str(item.get("role") or ""))
        content = str(item.get("content") or "")
        if role and content:
            out.append({"role": role, "content": content})
    return out


def _make_parse_messages(raw_reference: str, target: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PARSE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Parse this raw reference string into JSON with keys "
                "title, year, doi, author_tokens, type. Return JSON only.\n"
                f"Raw reference: {raw_reference}"
            ),
        },
        {"role": "assistant", "content": json.dumps(target, ensure_ascii=False, sort_keys=True)},
    ]


def _looks_reasonable_reference(raw_reference: str, target: dict[str, Any], *, max_raw_chars: int, min_title_chars: int) -> bool:
    if not raw_reference or len(raw_reference) < 20:
        return False
    if len(raw_reference) > max(200, max_raw_chars):
        return False
    title = _normalize_ws(str(target.get("title") or ""))
    if len(title) < max(2, min_title_chars):
        return False
    if URL_RE.search(title):
        return False
    return True


def load_parse_examples_from_jsonl(
    *,
    paths: list[Path],
    tier: str,
    source_tag: str,
    max_raw_chars: int,
    min_title_chars: int,
) -> tuple[list[CurriculumExample], dict[str, int]]:
    examples: list[CurriculumExample] = []
    stats = {"rows": 0, "accepted": 0, "rejected": 0}
    for path in paths:
        rows = _read_jsonl(path)
        stats["rows"] += len(rows)
        for row in rows:
            messages = _extract_messages(row)
            if len(messages) < 3:
                stats["rejected"] += 1
                continue
            user = messages[1].get("content") or ""
            raw_reference = _extract_raw_reference(user)
            assistant = messages[2].get("content") or ""
            try:
                target_obj = json.loads(assistant)
            except Exception:
                stats["rejected"] += 1
                continue
            target = _canonical_parse_target(target_obj, raw_reference=raw_reference)
            if not target:
                stats["rejected"] += 1
                continue
            if not _looks_reasonable_reference(
                raw_reference,
                target,
                max_raw_chars=max_raw_chars,
                min_title_chars=min_title_chars,
            ):
                stats["rejected"] += 1
                continue
            meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
            ex = CurriculumExample(
                tier=tier,
                task="parse_reference_json",
                messages=_make_parse_messages(raw_reference, target),
                meta={
                    "tier": tier,
                    "task": "parse_reference_json",
                    "source": source_tag,
                    "source_path": str(path),
                    **meta,
                },
            )
            examples.append(ex)
            stats["accepted"] += 1
    return examples, stats


def _render_person(person: Any) -> str:
    if isinstance(person, dict):
        literal = _normalize_ws(str(person.get("literal") or ""))
        family = _normalize_ws(str(person.get("family") or ""))
        given = _normalize_ws(str(person.get("given") or ""))
        if literal:
            return literal
        if family and given:
            return f"{family}, {given}"
        return family or given
    if isinstance(person, str):
        return _normalize_ws(person)
    return ""


def _year_from_csl(entry: dict[str, Any]) -> int | None:
    issued = entry.get("issued")
    if isinstance(issued, dict):
        date_parts = issued.get("date-parts")
        if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
            return _safe_year(date_parts[0][0])
        raw = issued.get("raw")
        return _safe_year(raw)
    return None


def _target_from_csl(entry: dict[str, Any]) -> dict[str, Any] | None:
    title = _normalize_ws(str(entry.get("title") or ""))
    if not title:
        return None
    author_tokens = _safe_author_tokens(entry.get("author"))
    if not author_tokens:
        author_tokens = _safe_author_tokens(entry.get("editor"))
    return {
        "title": title,
        "year": _year_from_csl(entry),
        "doi": _safe_doi(entry.get("DOI") or entry.get("doi")),
        "author_tokens": author_tokens,
        "type": _normalize_ws(str(entry.get("type") or "")) or None,
    }


def _render_reference_from_csl(entry: dict[str, Any]) -> str:
    people: list[str] = []
    if isinstance(entry.get("author"), list):
        people = [_render_person(p) for p in entry["author"] if _render_person(p)]
    elif isinstance(entry.get("editor"), list):
        people = [_render_person(p) for p in entry["editor"] if _render_person(p)]
    people_text = "; ".join([p for p in people if p]).strip()
    title = _normalize_ws(str(entry.get("title") or ""))
    year = _year_from_csl(entry)
    year_text = str(year) if year else _normalize_ws(str(((entry.get("issued") or {}).get("raw") if isinstance(entry.get("issued"), dict) else "") or ""))
    venue_bits: list[str] = []
    for key in ("container-title", "collection-title", "publisher", "publisher-place", "volume", "issue", "page", "note"):
        value = entry.get(key)
        if value is None:
            continue
        text = _normalize_ws(str(value))
        if text:
            venue_bits.append(text)
    doi = _safe_doi(entry.get("DOI") or entry.get("doi"))
    parts: list[str] = []
    if people_text:
        parts.append(people_text)
    if year_text:
        parts.append(year_text)
    if title:
        parts.append(title)
    if venue_bits:
        parts.append(". ".join(venue_bits))
    if doi:
        parts.append(doi)
    return _normalize_ws(". ".join([p for p in parts if p])).strip(". ") + "."


def _split_windows(refs: list[str]) -> list[list[str]]:
    if not refs:
        return []
    n = len(refs)
    if n <= 8:
        return [refs]
    window = min(14, n)
    step = max(4, window - 4)
    out: list[list[str]] = []
    start = 0
    while start < n:
        block = refs[start : start + window]
        if len(block) >= 4:
            out.append(block)
        if start + window >= n:
            break
        start += step
    return out or [refs]


def _maybe_wrap_line(value: str, rnd: random.Random) -> str:
    width = rnd.choice([76, 82, 88, 94])
    if len(value) < width + 10:
        return value
    return textwrap.fill(value, width=width, subsequent_indent="    ")


def _build_reference_block(refs: list[str], variant: str, rnd: random.Random) -> str:
    lines: list[str] = []
    for idx, ref in enumerate(refs, start=1):
        text = _maybe_wrap_line(ref, rnd)
        if variant == "numbered":
            lines.append(f"{idx}. {text}")
        else:
            lines.append(text)
    return "\n".join(lines)


def _make_split_messages(reference_block: str, references: list[str]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Split the bibliography text below into one item per full reference.\n"
                "Return JSON only in the required schema.\n\n"
                f"Bibliography text:\n{reference_block}"
            ),
        },
        {"role": "assistant", "content": json.dumps({"references": references}, ensure_ascii=False)},
    ]


def load_gold_examples(gold_path: Path, seed: int) -> tuple[list[CurriculumExample], dict[str, int]]:
    stats = {"records": 0, "parse_examples": 0, "split_examples": 0}
    if not gold_path.exists():
        return [], stats

    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return [], stats

    rnd = random.Random(seed)
    out: list[CurriculumExample] = []
    stats["records"] = len(records)

    for record in records:
        if not isinstance(record, dict):
            continue
        article_id = _normalize_ws(str(record.get("article_id") or ""))
        source = _normalize_ws(str(record.get("source") or "user_gold")) or "user_gold"
        expected = record.get("expected_references")
        if not isinstance(expected, list):
            continue

        rendered_refs: list[str] = []
        for entry in expected:
            if not isinstance(entry, dict):
                continue
            rendered = _render_reference_from_csl(entry)
            target = _target_from_csl(entry)
            if not rendered or not target:
                continue
            rendered_refs.append(rendered)
            out.append(
                CurriculumExample(
                    tier="gold",
                    task="parse_reference_json",
                    messages=_make_parse_messages(rendered, target),
                    meta={
                        "tier": "gold",
                        "task": "parse_reference_json",
                        "source": source,
                        "article_id": article_id,
                        "generator": "gold_csl_render",
                    },
                )
            )
            stats["parse_examples"] += 1

        windows = _split_windows(rendered_refs)
        for subset in windows:
            variant = rnd.choice(["plain", "numbered"])
            block = _build_reference_block(subset, variant=variant, rnd=rnd)
            out.append(
                CurriculumExample(
                    tier="gold",
                    task="split_reference_chunk",
                    messages=_make_split_messages(block, subset),
                    meta={
                        "tier": "gold",
                        "task": "split_reference_chunk",
                        "source": source,
                        "article_id": article_id,
                        "generator": f"gold_csl_render_{variant}",
                    },
                )
            )
            stats["split_examples"] += 1
    return out, stats


def _dedupe_with_priority(examples: list[CurriculumExample]) -> tuple[list[CurriculumExample], dict[str, int]]:
    priority = {"gold": 3, "silver": 2, "synthetic": 1}
    table: dict[str, CurriculumExample] = {}
    collisions = 0
    for ex in examples:
        key = _example_key(ex)
        if key not in table:
            table[key] = ex
            continue
        collisions += 1
        kept = table[key]
        if priority.get(ex.tier, 0) > priority.get(kept.tier, 0):
            table[key] = ex
    return list(table.values()), {"collisions": collisions, "unique": len(table)}


def _split_train_eval(examples: list[CurriculumExample], eval_ratio: float, seed: int) -> tuple[list[CurriculumExample], list[CurriculumExample]]:
    if not examples:
        return [], []
    rnd = random.Random(seed)
    rows = examples[:]
    rnd.shuffle(rows)
    eval_n = int(round(len(rows) * max(0.0, min(0.5, eval_ratio))))
    if len(rows) >= 8:
        eval_n = max(1, min(len(rows) - 1, eval_n))
    else:
        eval_n = max(0, min(len(rows) - 1, eval_n))
    eval_rows = rows[:eval_n]
    train_rows = rows[eval_n:]
    return train_rows, eval_rows


def _weighted_stage_rows(
    train_by_tier: dict[str, list[CurriculumExample]],
    weights: dict[str, int],
    seed: int,
    max_rows: int = 0,
) -> list[CurriculumExample]:
    rows: list[CurriculumExample] = []
    for tier, examples in train_by_tier.items():
        weight = max(0, int(weights.get(tier, 0)))
        if weight <= 0:
            continue
        for ex in examples:
            for _ in range(weight):
                rows.append(copy.deepcopy(ex))
    rnd = random.Random(seed)
    rnd.shuffle(rows)
    if max_rows > 0 and len(rows) > max_rows:
        rows = rows[:max_rows]
    return rows


def _rows(examples: list[CurriculumExample]) -> list[dict[str, Any]]:
    return [x.to_row() for x in examples]


def _count_by(items: list[CurriculumExample], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        key = str(getattr(item, attr))
        out[key] = out.get(key, 0) + 1
    return out


def _default_if_empty(values: list[str], fallback: list[str]) -> list[str]:
    return values if values else fallback


def main() -> None:
    args = parse_args()
    seed = int(args.seed)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    silver_inputs = [Path(p).resolve() for p in _default_if_empty(args.silver_jsonl, ["data/reference_lora_train.jsonl", "data/reference_lora_eval.jsonl"])]
    synthetic_inputs = [Path(p).resolve() for p in _default_if_empty(args.synthetic_jsonl, ["data/reference_lora_pdf_samples.jsonl"])]
    gold_path = Path(args.gold_articles_json).resolve()

    silver_examples, silver_stats = load_parse_examples_from_jsonl(
        paths=silver_inputs,
        tier="silver",
        source_tag="silver_jsonl",
        max_raw_chars=max(300, int(args.max_raw_chars)),
        min_title_chars=max(2, int(args.min_title_chars)),
    )
    synthetic_examples, synthetic_stats = load_parse_examples_from_jsonl(
        paths=synthetic_inputs,
        tier="synthetic",
        source_tag="synthetic_jsonl",
        max_raw_chars=max(300, int(args.max_raw_chars)),
        min_title_chars=max(2, int(args.min_title_chars)),
    )
    gold_examples, gold_stats = load_gold_examples(gold_path, seed=seed)

    all_examples = silver_examples + synthetic_examples + gold_examples
    deduped, dedupe_stats = _dedupe_with_priority(all_examples)

    by_tier: dict[str, list[CurriculumExample]] = {"gold": [], "silver": [], "synthetic": []}
    for ex in deduped:
        by_tier.setdefault(ex.tier, []).append(ex)

    train_by_tier: dict[str, list[CurriculumExample]] = {}
    eval_rows: list[CurriculumExample] = []
    for tier, rows in by_tier.items():
        train_rows, tier_eval = _split_train_eval(rows, eval_ratio=float(args.eval_ratio), seed=seed + len(tier))
        train_by_tier[tier] = train_rows
        eval_rows.extend(tier_eval)

    rnd = random.Random(seed + 99)
    rnd.shuffle(eval_rows)

    stage1_weights = _parse_weight_map(args.stage1_weights)
    stage2_weights = _parse_weight_map(args.stage2_weights)

    stage1_train = _weighted_stage_rows(
        train_by_tier,
        weights=stage1_weights,
        seed=seed + 1001,
        max_rows=max(0, int(args.stage1_max_train)),
    )
    stage2_train = _weighted_stage_rows(
        train_by_tier,
        weights=stage2_weights,
        seed=seed + 2001,
        max_rows=max(0, int(args.stage2_max_train)),
    )

    stage1_eval = copy.deepcopy(eval_rows)
    stage2_eval = copy.deepcopy(eval_rows)
    eval_parse = [x for x in eval_rows if x.task == "parse_reference_json"]
    eval_split = [x for x in eval_rows if x.task == "split_reference_chunk"]

    paths = {
        "stage1_train": output_dir / "stage1_train.jsonl",
        "stage1_eval": output_dir / "stage1_eval.jsonl",
        "stage2_train": output_dir / "stage2_train.jsonl",
        "stage2_eval": output_dir / "stage2_eval.jsonl",
        "eval_parse": output_dir / "eval_parse.jsonl",
        "eval_split": output_dir / "eval_split.jsonl",
        "gold_pool": output_dir / "gold_pool.jsonl",
        "silver_pool": output_dir / "silver_pool.jsonl",
        "synthetic_pool": output_dir / "synthetic_pool.jsonl",
    }
    _write_jsonl(paths["stage1_train"], _rows(stage1_train))
    _write_jsonl(paths["stage1_eval"], _rows(stage1_eval))
    _write_jsonl(paths["stage2_train"], _rows(stage2_train))
    _write_jsonl(paths["stage2_eval"], _rows(stage2_eval))
    _write_jsonl(paths["eval_parse"], _rows(eval_parse))
    _write_jsonl(paths["eval_split"], _rows(eval_split))
    _write_jsonl(paths["gold_pool"], _rows(by_tier.get("gold", [])))
    _write_jsonl(paths["silver_pool"], _rows(by_tier.get("silver", [])))
    _write_jsonl(paths["synthetic_pool"], _rows(by_tier.get("synthetic", [])))

    summary = {
        "seed": seed,
        "output_dir": str(output_dir),
        "inputs": {
            "silver_jsonl": [str(x) for x in silver_inputs],
            "synthetic_jsonl": [str(x) for x in synthetic_inputs],
            "gold_articles_json": str(gold_path),
        },
        "filters": {
            "eval_ratio": float(args.eval_ratio),
            "max_raw_chars": int(args.max_raw_chars),
            "min_title_chars": int(args.min_title_chars),
        },
        "weights": {
            "stage1": stage1_weights,
            "stage2": stage2_weights,
        },
        "input_stats": {
            "silver": silver_stats,
            "synthetic": synthetic_stats,
            "gold": gold_stats,
        },
        "dedupe": dedupe_stats,
        "pool_counts": {
            "all": len(deduped),
            "by_tier": {k: len(v) for k, v in by_tier.items()},
            "by_task": _count_by(deduped, "task"),
        },
        "train_eval_counts": {
            "train_by_tier": {k: len(v) for k, v in train_by_tier.items()},
            "eval_total": len(eval_rows),
            "eval_parse": len(eval_parse),
            "eval_split": len(eval_split),
        },
        "stage_counts": {
            "stage1_train": len(stage1_train),
            "stage1_eval": len(stage1_eval),
            "stage2_train": len(stage2_train),
            "stage2_eval": len(stage2_eval),
            "stage1_by_task": _count_by(stage1_train, "task"),
            "stage2_by_task": _count_by(stage2_train, "task"),
        },
        "outputs": {k: str(v) for k, v in paths.items()},
    }
    summary_path = output_dir / "curriculum_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
