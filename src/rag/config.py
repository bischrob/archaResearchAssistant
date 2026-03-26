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
    return raw.strip().lower() in {'1', 'true', 'yes'}


def _env_not_false(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() not in {'0', 'false', 'no'}


@dataclass(frozen=True)
class Settings:
    pdf_source_dir: str = field(default_factory=lambda: _env_str('PDF_SOURCE_DIR', _env_str('NEXTCLOUD_PDF_ROOT', r'\192.168.0.37\pooled\media\Books\pdfs')).strip())
    neo4j_uri: str = field(default_factory=lambda: _env_str('NEO4J_URI', 'bolt://localhost:7687'))
    neo4j_user: str = field(default_factory=lambda: _env_str('NEO4J_USER', 'neo4j'))
    neo4j_password: str = field(default_factory=lambda: _env_str('NEO4J_PASSWORD', 'archaResearchAssistant'))
    embedding_provider: str = field(default_factory=lambda: _env_str('EMBEDDING_PROVIDER', 'sentence_transformers').strip().lower())
    embedding_model: str = field(default_factory=lambda: _env_str('EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2'))
    embedding_device: str = field(default_factory=lambda: _env_str('EMBEDDING_DEVICE', 'cpu').strip().lower())
    embedding_batch_size: int = field(default_factory=lambda: _env_int('EMBEDDING_BATCH_SIZE', 8))
    embedding_normalize: bool = field(default_factory=lambda: _env_not_false('EMBEDDING_NORMALIZE', True))
    paperpile_json: str = field(default_factory=lambda: _env_str('PAPERPILE_JSON', 'Paperpile.json'))
    metadata_backend: str = field(default_factory=lambda: _env_str('METADATA_BACKEND', 'zotero').strip().lower())
    metadata_require_match: bool = field(default_factory=lambda: _env_not_false('METADATA_REQUIRE_MATCH', True))
    zotero_require_persistent_id: bool = field(default_factory=lambda: _env_not_false('ZOTERO_REQUIRE_PERSISTENT_ID', True))
    zotero_db_path: str = field(default_factory=lambda: _env_str('ZOTERO_DB_PATH', _env_str('ZOTERO_LOCAL_DB_PATH', '')).strip())
    zotero_storage_root: str = field(default_factory=lambda: _env_str('ZOTERO_STORAGE_ROOT', _env_str('ZOTERO_STORAGE_DIR', '')).strip())
    zotero_webdav_url: str = field(default_factory=lambda: _env_str('ZOTERO_WEBDAV_URL', '').strip())
    zotero_webdav_username: str = field(default_factory=lambda: _env_str('ZOTERO_WEBDAV_USERNAME', '').strip())
    zotero_webdav_password: str = field(default_factory=lambda: _env_str('ZOTERO_WEBDAV_PASSWORD', '').strip())
    zotero_webdav_cache_dir: str = field(default_factory=lambda: _env_str('ZOTERO_WEBDAV_CACHE_DIR', 'data/zotero_webdav_cache').strip())
    zotero_linked_path_map_json: str = field(default_factory=lambda: _env_str('ZOTERO_LINKED_PATH_MAP_JSON', '').strip())
    zotero_attachment_override_json: str = field(default_factory=lambda: _env_str('ZOTERO_ATTACHMENT_OVERRIDE_JSON', 'data/zotero_attachment_path_overrides.json').strip())
    chunk_size_words: int = field(default_factory=lambda: _env_int('CHUNK_SIZE_WORDS', 220))
    chunk_overlap_words: int = field(default_factory=lambda: _env_int('CHUNK_OVERLAP_WORDS', 45))
    citation_min_quality: float = field(default_factory=lambda: _env_float('CITATION_MIN_QUALITY', 0.35))
    chunk_strip_page_noise: bool = field(default_factory=lambda: _env_not_false('CHUNK_STRIP_PAGE_NOISE', True))
    citation_parser: str = field(default_factory=lambda: _env_str('CITATION_PARSER', 'openclaw_refsplit_anystyle').strip().lower())
    text_acquisition_policy: str = field(default_factory=lambda: _env_str('TEXT_ACQUISITION_POLICY', 'native_pdf_then_paddle_if_malformed').strip().lower())
    text_quality_check_backend: str = field(default_factory=lambda: _env_str('TEXT_QUALITY_CHECK_BACKEND', 'heuristic_placeholder').strip().lower())
    paddleocr_text_dir: str = field(default_factory=lambda: _env_str('PADDLEOCR_TEXT_DIR', 'ocr/paddleocr/text').strip())
    paddleocr_text_fallback_dir: str = field(default_factory=lambda: _env_str('PADDLEOCR_TEXT_FALLBACK_DIR', 'data/ocr/paddleocr/text').strip())
    paddleocr_prefer_text: bool = field(default_factory=lambda: _env_not_false('PADDLEOCR_PREFER_TEXT', True))
    paddleocr_auto_generate_missing_text: bool = field(default_factory=lambda: _env_not_false('PADDLEOCR_AUTO_GENERATE_MISSING_TEXT', True))
    paddleocr_auto_lang: str = field(default_factory=lambda: _env_str('PADDLEOCR_AUTO_LANG', 'en').strip() or 'en')
    paddleocr_auto_device: str = field(default_factory=lambda: _env_str('PADDLEOCR_AUTO_DEVICE', 'cpu').strip().lower() or 'cpu')
    paddleocr_auto_render_dpi: int = field(default_factory=lambda: _env_int('PADDLEOCR_AUTO_RENDER_DPI', 180))
    anystyle_service: str = field(default_factory=lambda: _env_str('ANYSTYLE_SERVICE', 'anystyle').strip() or 'anystyle')
    anystyle_gpu_service: str = field(default_factory=lambda: _env_str('ANYSTYLE_GPU_SERVICE', 'anystyle-gpu').strip() or 'anystyle-gpu')
    anystyle_timeout_seconds: int = field(default_factory=lambda: _env_int('ANYSTYLE_TIMEOUT_SECONDS', 240))
    anystyle_require_success: bool = field(default_factory=lambda: _env_bool('ANYSTYLE_REQUIRE_SUCCESS', False))
    anystyle_use_gpu: bool = field(default_factory=lambda: _env_bool('ANYSTYLE_USE_GPU', False))
    anystyle_gpu_devices: str = field(default_factory=lambda: _env_str('ANYSTYLE_GPU_DEVICES', 'all').strip() or 'all')
    query_preprocess_backend: str = field(default_factory=lambda: _env_str('QUERY_PREPROCESS_BACKEND', 'openclaw_agent').strip().lower())
    openclaw_agent_command: str = field(default_factory=lambda: _env_str('OPENCLAW_AGENT_COMMAND', '').strip())
    openclaw_agent_preprocess_cmd: str = field(default_factory=lambda: _env_str('OPENCLAW_AGENT_PREPROCESS_CMD', '').strip())
    openclaw_agent_answer_cmd: str = field(default_factory=lambda: _env_str('OPENCLAW_AGENT_ANSWER_CMD', '').strip())
    zip_pdf_enable: bool = field(default_factory=lambda: _env_not_false('ZIP_PDF_ENABLE', True))
    zip_pdf_cache_dir: str = field(default_factory=lambda: _env_str('ZIP_PDF_CACHE_DIR', '.cache/zotero_zip_pdf_cache').strip())
    keyword_max_terms: int = field(default_factory=lambda: _env_int('KEYWORD_MAX_TERMS', 32))
