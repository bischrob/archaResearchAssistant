# Model Setup

This project can run with OpenAI-backed answering alone, but local Qwen features require a local Qwen3 base model and, for citation extraction, a LoRA adapter.

## What you need

- `QWEN3_MODEL_PATH`
- `QWEN3_CITATION_ADAPTER_PATH` for local citation extraction
- optionally `QWEN3_QUERY_ADAPTER_PATH` for local query preprocessing

## Base model

Bring your own Qwen3 base model and point `QWEN3_MODEL_PATH` at the local model directory.

Set in `.env`:

```bash
QWEN3_MODEL_PATH=/path/to/qwen3-base-model
```

Disk expectations:

- base model: several GB
- local repo example currently uses a base model directory around 7-8 GB

## LoRA adapter

Recommended release asset:

- https://github.com/bischrob/archaResearchAssistant/releases/tag/lora-20260319-104710

Download:

- `qwen3-reference-split-500-cpu_49006992-lora-20260319-104710.tar.gz`
- `qwen3-reference-split-500-cpu_49006992-lora-20260319-104710.tar.gz.sha256`

Verify:

```bash
sha256sum -c qwen3-reference-split-500-cpu_49006992-lora-20260319-104710.tar.gz.sha256
```

Unpack and set:

```bash
QWEN3_CITATION_ADAPTER_PATH=/path/to/unpacked/adapter
```

Disk expectations:

- adapter package: about 117 MB compressed
- adapter weights: about 126 MB uncompressed for the current release

## Runtime behavior

- If `QWEN3_CITATION_ADAPTER_PATH` is set, local citation extraction can use the adapter.
- If it is not set, runtime may auto-select the newest local adapter found under `models/` when available.
- If you do not want local Qwen citation parsing, use the OpenAI-only and/or Anystyle-supported flows instead.
