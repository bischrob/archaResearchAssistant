from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in {"1", "true", "yes"}


def _env_not_false(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = field(default_factory=lambda: _env_str("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = field(default_factory=lambda: _env_str("NEO4J_USER", "neo4j"))
    neo4j_password: str = field(default_factory=lambda: _env_str("NEO4J_PASSWORD", "archaResearchAssistant"))
    embedding_model: str = field(
        default_factory=lambda: _env_str("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    )
    paperpile_json: str = field(default_factory=lambda: _env_str("PAPERPILE_JSON", "Paperpile.json"))
    chunk_size_words: int = field(default_factory=lambda: _env_int("CHUNK_SIZE_WORDS", 220))
    chunk_overlap_words: int = field(default_factory=lambda: _env_int("CHUNK_OVERLAP_WORDS", 45))
    citation_min_quality: float = field(default_factory=lambda: _env_float("CITATION_MIN_QUALITY", 0.35))
    chunk_strip_page_noise: bool = field(default_factory=lambda: _env_not_false("CHUNK_STRIP_PAGE_NOISE", True))
    citation_parser: str = field(default_factory=lambda: _env_str("CITATION_PARSER", "anystyle").strip().lower())
    anystyle_service: str = field(default_factory=lambda: _env_str("ANYSTYLE_SERVICE", "anystyle").strip() or "anystyle")
    anystyle_gpu_service: str = field(
        default_factory=lambda: _env_str("ANYSTYLE_GPU_SERVICE", "anystyle-gpu").strip() or "anystyle-gpu"
    )
    anystyle_timeout_seconds: int = field(default_factory=lambda: _env_int("ANYSTYLE_TIMEOUT_SECONDS", 240))
    anystyle_require_success: bool = field(default_factory=lambda: _env_bool("ANYSTYLE_REQUIRE_SUCCESS", False))
    anystyle_use_gpu: bool = field(default_factory=lambda: _env_bool("ANYSTYLE_USE_GPU", False))
    anystyle_gpu_devices: str = field(default_factory=lambda: _env_str("ANYSTYLE_GPU_DEVICES", "all").strip() or "all")
    query_preprocess_backend: str = field(
        default_factory=lambda: _env_str("QUERY_PREPROCESS_BACKEND", "openai").strip().lower()
    )
    qwen_model_path: str = field(default_factory=lambda: _env_str("QWEN3_MODEL_PATH", "").strip())
    qwen_device: str = field(default_factory=lambda: _env_str("QWEN3_DEVICE", "auto").strip().lower())
    qwen_dtype: str = field(default_factory=lambda: _env_str("QWEN3_DTYPE", "auto").strip().lower())
    qwen_max_input_chars: int = field(default_factory=lambda: _env_int("QWEN3_MAX_INPUT_CHARS", 12000))
    qwen_query_model_path: str = field(default_factory=lambda: _env_str("QWEN3_QUERY_MODEL_PATH", "").strip())
    qwen_query_adapter_path: str = field(default_factory=lambda: _env_str("QWEN3_QUERY_ADAPTER_PATH", "").strip())
    qwen_query_max_new_tokens: int = field(default_factory=lambda: _env_int("QWEN3_QUERY_MAX_NEW_TOKENS", 96))
    qwen_citation_model_path: str = field(default_factory=lambda: _env_str("QWEN3_CITATION_MODEL_PATH", "").strip())
    qwen_citation_adapter_path: str = field(
        default_factory=lambda: _env_str("QWEN3_CITATION_ADAPTER_PATH", "").strip()
    )
    qwen_citation_max_new_tokens: int = field(
        default_factory=lambda: _env_int("QWEN3_CITATION_MAX_NEW_TOKENS", 768)
    )
    qwen_citation_batch_size: int = field(default_factory=lambda: _env_int("QWEN3_CITATION_BATCH_SIZE", 24))
    qwen_require_success: bool = field(default_factory=lambda: _env_bool("QWEN3_REQUIRE_SUCCESS", False))
