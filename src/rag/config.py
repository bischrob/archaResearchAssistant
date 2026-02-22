from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_user: str = os.getenv("NEO4J_USER", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "archaResearchAssistant")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    paperpile_json: str = os.getenv("PAPERPILE_JSON", "Paperpile.json")
    chunk_size_words: int = int(os.getenv("CHUNK_SIZE_WORDS", "220"))
    chunk_overlap_words: int = int(os.getenv("CHUNK_OVERLAP_WORDS", "45"))
    citation_min_quality: float = float(os.getenv("CITATION_MIN_QUALITY", "0.35"))
    chunk_strip_page_noise: bool = os.getenv("CHUNK_STRIP_PAGE_NOISE", "1").strip().lower() not in {"0", "false", "no"}
    citation_parser: str = os.getenv("CITATION_PARSER", "anystyle").strip().lower()
    anystyle_service: str = os.getenv("ANYSTYLE_SERVICE", "anystyle").strip() or "anystyle"
    anystyle_timeout_seconds: int = int(os.getenv("ANYSTYLE_TIMEOUT_SECONDS", "240"))
    anystyle_require_success: bool = os.getenv("ANYSTYLE_REQUIRE_SUCCESS", "0").strip().lower() in {"1", "true", "yes"}
