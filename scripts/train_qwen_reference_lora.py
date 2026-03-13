#!/usr/bin/env python3
from __future__ import annotations

import argparse
import inspect
import json
import random
import re
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
from torch.utils.data import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)

DEFAULT_SYSTEM_PROMPT = (
    "You are a bibliography parser. Convert each raw reference string into compact JSON with fields: "
    "title, year, doi, author_tokens, and type."
)
WINDOWS_DRIVE_RE = re.compile(r"^([A-Za-z]):[\\/](.+)$")


def resolve_local_model_path(path_str: str) -> Path:
    """Resolve local/WSL model paths without importing runtime RAG modules."""
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a Qwen LoRA adapter for reference extraction.")
    parser.add_argument("--model-path", required=True, help="Base Qwen model path (Windows path or local path).")
    parser.add_argument("--train-jsonl", required=True, help="Training dataset JSONL file.")
    parser.add_argument("--eval-jsonl", default="", help="Optional validation dataset JSONL file.")
    parser.add_argument("--output-dir", required=True, help="Directory to write the LoRA adapter.")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--load-in-4bit",
        action="store_true",
        help="Use bitsandbytes 4-bit quantization (QLoRA-friendly). Recommended for 8GB GPUs.",
    )
    parser.add_argument(
        "--bnb-4bit-compute-dtype",
        default="auto",
        choices=["auto", "fp16", "bf16"],
        help="Computation dtype for 4-bit quantization.",
    )
    parser.add_argument(
        "--gradient-checkpointing",
        action="store_true",
        help="Enable gradient checkpointing to reduce activation memory.",
    )
    parser.add_argument(
        "--target-modules",
        default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
        help="Comma-separated module names for LoRA injection.",
    )
    parser.add_argument(
        "--init-adapter-path",
        default="",
        help="Optional existing LoRA adapter path to continue training from.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def _normalize_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    messages = record.get("messages")
    if isinstance(messages, list):
        out = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "")
            if role and content:
                out.append({"role": role, "content": content})
        return out

    prompt = str(record.get("input") or record.get("prompt") or record.get("raw_reference") or "").strip()
    output = record.get("output")
    if output is None:
        output = record.get("target")
    if isinstance(output, (dict, list)):
        output_text = json.dumps(output, ensure_ascii=False)
    else:
        output_text = str(output or "").strip()
    if not prompt or not output_text:
        return []

    system_prompt = str(record.get("system") or DEFAULT_SYSTEM_PROMPT).strip()
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": output_text},
    ]


def _prompt_text(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return "\n".join(f"{m['role']}: {m['content']}" for m in messages) + "\nassistant:"


def _encode_supervised_example(
    tokenizer: Any,
    messages: list[dict[str, str]],
    max_length: int,
) -> dict[str, list[int]] | None:
    if not messages:
        return None
    if messages[-1].get("role") != "assistant":
        return None

    prompt_messages = messages[:-1]
    answer_text = str(messages[-1].get("content") or "").strip()
    if not answer_text:
        return None

    prompt_ids = tokenizer(
        _prompt_text(tokenizer, prompt_messages),
        add_special_tokens=False,
    )["input_ids"]
    answer_suffix = tokenizer.eos_token or ""
    answer_ids = tokenizer(
        answer_text + answer_suffix,
        add_special_tokens=False,
    )["input_ids"]

    input_ids = prompt_ids + answer_ids
    labels = ([-100] * len(prompt_ids)) + answer_ids

    if len(input_ids) > max_length:
        trim = len(input_ids) - max_length
        input_ids = input_ids[trim:]
        labels = labels[trim:]
    if not input_ids or all(label == -100 for label in labels):
        return None

    return {
        "input_ids": input_ids,
        "labels": labels,
        "attention_mask": [1] * len(input_ids),
    }


class JsonlSupervisedDataset(Dataset):
    def __init__(self, path: Path, tokenizer: Any, max_length: int) -> None:
        rows = []
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    rows.append(row)

        samples = []
        for row in rows:
            messages = _normalize_messages(row)
            encoded = _encode_supervised_example(tokenizer, messages, max_length=max_length)
            if encoded:
                samples.append(encoded)

        if not samples:
            raise ValueError(f"No trainable examples found in {path}")
        self.samples = samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> dict[str, list[int]]:
        return self.samples[idx]


class SupervisedCollator:
    def __init__(self, pad_token_id: int) -> None:
        self.pad_token_id = int(pad_token_id)

    def __call__(self, features: list[dict[str, list[int]]]) -> dict[str, torch.Tensor]:
        max_len = max(len(x["input_ids"]) for x in features)
        input_ids = []
        attention_mask = []
        labels = []
        for row in features:
            length = len(row["input_ids"])
            pad = max_len - length
            input_ids.append(row["input_ids"] + ([self.pad_token_id] * pad))
            attention_mask.append(row["attention_mask"] + ([0] * pad))
            labels.append(row["labels"] + ([-100] * pad))
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def _enable_input_require_grads(model: Any) -> None:
    """Ensure checkpointed forward pass retains grad flow for LoRA-only training."""
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()
        return

    input_embeddings = model.get_input_embeddings()
    if input_embeddings is None:
        return

    def _require_grads(_: Any, __: Any, output: Any) -> Any:
        if hasattr(output, "requires_grad_"):
            output.requires_grad_(True)
        return output

    input_embeddings.register_forward_hook(_require_grads)


def _seed_all(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_json_safe(v) for v in value)
    return value


def main() -> None:
    args = parse_args()
    _seed_all(args.seed)

    model_path = resolve_local_model_path(args.model_path)
    init_adapter_path = resolve_local_model_path(args.init_adapter_path) if args.init_adapter_path else None
    train_path = Path(args.train_jsonl).resolve()
    eval_path = Path(args.eval_jsonl).resolve() if args.eval_jsonl else None
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token_id is None and tokenizer.eos_token is not None:
        tokenizer.pad_token = tokenizer.eos_token
    if tokenizer.pad_token_id is None:
        tokenizer.add_special_tokens({"pad_token": "<|pad|>"})

    use_bf16 = torch.cuda.is_available() and torch.cuda.is_bf16_supported()
    use_fp16 = torch.cuda.is_available() and not use_bf16
    torch_dtype = torch.bfloat16 if use_bf16 else (torch.float16 if use_fp16 else None)

    model_kwargs: dict[str, Any] = {
        "trust_remote_code": True,
    }
    if torch_dtype is not None:
        model_kwargs["torch_dtype"] = torch_dtype

    if args.load_in_4bit:
        if args.bnb_4bit_compute_dtype == "bf16":
            compute_dtype = torch.bfloat16
        elif args.bnb_4bit_compute_dtype == "fp16":
            compute_dtype = torch.float16
        else:
            compute_dtype = torch.bfloat16 if use_bf16 else torch.float16
        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        model_kwargs["device_map"] = "auto"

    model = AutoModelForCausalLM.from_pretrained(str(model_path), **model_kwargs)
    if args.load_in_4bit:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=bool(args.gradient_checkpointing),
        )
    if tokenizer.vocab_size > model.get_input_embeddings().weight.shape[0]:
        model.resize_token_embeddings(len(tokenizer))

    if init_adapter_path:
        model = PeftModel.from_pretrained(model, str(init_adapter_path), is_trainable=True)
        lora_cfg_obj = None
        if hasattr(model, "peft_config") and isinstance(model.peft_config, dict) and model.peft_config:
            lora_cfg_obj = next(iter(model.peft_config.values()))
    else:
        lora_cfg_obj = LoraConfig(
            r=max(1, int(args.lora_r)),
            lora_alpha=max(1, int(args.lora_alpha)),
            lora_dropout=max(0.0, float(args.lora_dropout)),
            task_type="CAUSAL_LM",
            bias="none",
            target_modules=[x.strip() for x in args.target_modules.split(",") if x.strip()],
        )
        model = get_peft_model(model, lora_cfg_obj)

    if args.gradient_checkpointing:
        _enable_input_require_grads(model)
        model.config.use_cache = False
        model.gradient_checkpointing_enable()

    model.print_trainable_parameters()

    train_dataset = JsonlSupervisedDataset(train_path, tokenizer=tokenizer, max_length=max(128, int(args.max_length)))
    eval_dataset = None
    if eval_path:
        eval_dataset = JsonlSupervisedDataset(eval_path, tokenizer=tokenizer, max_length=max(128, int(args.max_length)))

    kwargs: dict[str, Any] = {
        "output_dir": str(output_dir),
        "num_train_epochs": float(args.epochs),
        "per_device_train_batch_size": max(1, int(args.batch_size)),
        "per_device_eval_batch_size": max(1, int(args.batch_size)),
        "gradient_accumulation_steps": max(1, int(args.grad_accum)),
        "learning_rate": float(args.learning_rate),
        "warmup_ratio": max(0.0, float(args.warmup_ratio)),
        "weight_decay": max(0.0, float(args.weight_decay)),
        "logging_steps": 10,
        "save_strategy": "epoch",
        "load_best_model_at_end": (eval_dataset is not None),
        "metric_for_best_model": ("eval_loss" if eval_dataset is not None else None),
        "greater_is_better": False,
        "bf16": use_bf16,
        "fp16": use_fp16,
        "remove_unused_columns": False,
        "report_to": [],
        "seed": args.seed,
        "gradient_checkpointing": bool(args.gradient_checkpointing),
    }
    if args.load_in_4bit:
        kwargs["optim"] = "paged_adamw_8bit"
    eval_value = "epoch" if eval_dataset is not None else "no"
    sig = inspect.signature(TrainingArguments.__init__).parameters
    if "evaluation_strategy" in sig:
        kwargs["evaluation_strategy"] = eval_value
    elif "eval_strategy" in sig:
        kwargs["eval_strategy"] = eval_value
    else:
        raise RuntimeError("Unsupported transformers TrainingArguments: missing evaluation strategy argument.")
    training_args = TrainingArguments(**kwargs)

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=SupervisedCollator(tokenizer.pad_token_id),
    )
    trainer.train()
    trainer.model.save_pretrained(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))
    train_metrics = _json_safe(trainer.state.log_history[-1] if trainer.state.log_history else {})
    with (output_dir / "training_run.json").open("w", encoding="utf-8") as f:
        json.dump(
            {
                "model_path": str(model_path),
                "train_jsonl": str(train_path),
                "eval_jsonl": str(eval_path) if eval_path else None,
                "init_adapter_path": str(init_adapter_path) if init_adapter_path else None,
                "args": vars(args),
                "train_samples": len(train_dataset),
                "eval_samples": len(eval_dataset) if eval_dataset is not None else 0,
                "lora_config": _json_safe(lora_cfg_obj.to_dict()) if lora_cfg_obj else {},
                "final_metrics": train_metrics,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    main()
