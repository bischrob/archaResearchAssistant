from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import fitz

from .config import Settings


SUSPECT_CHAR_RE = re.compile(r"[\uFFFD\x00-\x08\x0B\x0C\x0E-\x1F]")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")


@dataclass(frozen=True)
class TextQualityReport:
    backend: str
    is_malformed: bool
    reason: str
    char_count: int
    alpha_ratio: float
    suspect_char_ratio: float
    token_count: int
    page_with_text_count: int
    total_page_count: int


@dataclass(frozen=True)
class TextAcquisitionResult:
    lines_with_page: list[tuple[int, str]]
    method: str
    fallback_used: bool
    native_text_report: TextQualityReport
    ocr_text_path: str | None = None


def extract_native_pdf_lines(pdf_path: Path, *, strip_page_noise: bool = True) -> list[tuple[int, str]]:
    from .pdf_processing import build_lines_with_page

    page_text: list[tuple[int, str]] = []
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc):
            text = page.get_text("text")
            if text and text.strip():
                page_text.append((idx + 1, text))
    return build_lines_with_page(page_text, strip_page_noise=strip_page_noise)


def _normalize_lookup_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _candidate_ocr_dirs(settings: Settings) -> list[Path]:
    dirs: list[Path] = []
    for raw in [settings.paddleocr_text_dir, settings.paddleocr_text_fallback_dir]:
        raw = (raw or "").strip()
        if not raw:
            continue
        p = Path(raw).resolve()
        if p not in dirs:
            dirs.append(p)
    return dirs


def locate_ocr_text(pdf_path: Path, settings: Settings) -> Path | None:
    pdf_key = _normalize_lookup_key(pdf_path.stem)
    if not pdf_key:
        return None

    for root in _candidate_ocr_dirs(settings):
        direct = root / f"{pdf_path.stem}.txt"
        if direct.exists() and direct.is_file():
            return direct
        if root.exists() and root.is_dir():
            for item in root.rglob("*.txt"):
                if _normalize_lookup_key(item.stem) == pdf_key:
                    return item.resolve()
    return None


def load_ocr_lines(ocr_text_path: Path) -> list[tuple[int, str]]:
    raw = ocr_text_path.read_text(encoding="utf-8", errors="ignore")
    lines = [line.strip() for line in raw.splitlines() if line and line.strip()]
    return [(1, line) for line in lines]


def _paddleocr_use_gpu(device: str) -> bool:
    d = (device or "").strip().lower()
    if d == "gpu":
        return True
    if d == "cpu":
        return False
    try:
        import paddle  # type: ignore

        return bool(paddle.device.is_compiled_with_cuda())
    except Exception:
        return False


def _build_paddleocr_pipeline(lang: str, device: str) -> object:
    try:
        from paddleocr import PaddleOCR  # type: ignore
    except Exception as exc:
        raise RuntimeError("PaddleOCR is not installed in this environment.") from exc

    use_gpu = _paddleocr_use_gpu(device)
    try:
        return PaddleOCR(
            lang=lang,
            device="gpu:0" if use_gpu else "cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except TypeError:
        return PaddleOCR(use_angle_cls=True, lang=lang, use_gpu=use_gpu)


def _extract_lines_from_paddle_page_payload(payload: object) -> list[str]:
    if not isinstance(payload, list):
        return []
    lines: list[str] = []
    for item in payload:
        if not isinstance(item, list) or len(item) < 2:
            continue
        line_payload = item[1]
        if isinstance(line_payload, list) and line_payload:
            text = str(line_payload[0]).strip()
            if text:
                lines.append(text)
    return lines


def generate_ocr_text_sidecar(pdf_path: Path, settings: Settings) -> Path | None:
    if not settings.paddleocr_auto_generate_missing_text:
        return None
    try:
        pipeline = _build_paddleocr_pipeline(settings.paddleocr_auto_lang, settings.paddleocr_auto_device)
    except Exception:
        return None

    dpi = max(96, int(settings.paddleocr_auto_render_dpi))
    scale = dpi / 72.0
    collected: list[str] = []
    try:
        with fitz.open(pdf_path) as doc:
            with tempfile.TemporaryDirectory(prefix="paddleocr_pages_") as temp_dir:
                tmp = Path(temp_dir)
                for page_idx, page in enumerate(doc):
                    image_path = tmp / f"page_{page_idx:05d}.png"
                    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    pix.save(str(image_path))
                    payload = pipeline.ocr(str(image_path), cls=True)
                    for line in _extract_lines_from_paddle_page_payload(payload if isinstance(payload, list) else []):
                        if line:
                            collected.append(line)
    except Exception:
        return None

    body = "\n".join(collected).strip()
    if not body:
        return None

    roots = _candidate_ocr_dirs(settings)
    target_root = roots[0] if roots else Path("ocr/paddleocr/text").resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    out_path = target_root / f"{pdf_path.stem}.txt"
    out_path.write_text(body + "\n", encoding="utf-8")
    return out_path


def assess_text_quality(lines_with_page: list[tuple[int, str]], *, total_page_count: int, backend: str) -> TextQualityReport:
    text = "\n".join(line for _, line in lines_with_page if line).strip()
    char_count = len(text)
    alpha_count = sum(1 for ch in text if ch.isalpha())
    suspect_count = len(SUSPECT_CHAR_RE.findall(text))
    token_count = len(TOKEN_RE.findall(text))
    page_with_text_count = len({page for page, line in lines_with_page if line.strip()})
    alpha_ratio = (alpha_count / char_count) if char_count else 0.0
    suspect_ratio = (suspect_count / char_count) if char_count else 0.0

    malformed = False
    reasons: list[str] = []
    min_expected_tokens = max(40, total_page_count * 20)

    if char_count < 200:
        malformed = True
        reasons.append("native_text_too_short")
    if token_count < min_expected_tokens:
        malformed = True
        reasons.append("native_token_count_too_low")
    if char_count and alpha_ratio < 0.45:
        malformed = True
        reasons.append("alpha_ratio_too_low")
    if char_count and suspect_ratio > 0.02:
        malformed = True
        reasons.append("suspect_char_ratio_too_high")
    if total_page_count >= 2 and page_with_text_count <= max(1, total_page_count // 4):
        malformed = True
        reasons.append("too_few_pages_with_text")

    if not reasons:
        reasons.append("native_text_looks_usable")

    return TextQualityReport(
        backend=backend,
        is_malformed=malformed,
        reason=",".join(reasons),
        char_count=char_count,
        alpha_ratio=round(alpha_ratio, 4),
        suspect_char_ratio=round(suspect_ratio, 4),
        token_count=token_count,
        page_with_text_count=page_with_text_count,
        total_page_count=total_page_count,
    )


def acquire_pdf_text(pdf_path: Path, *, settings: Settings, strip_page_noise: bool = True) -> TextAcquisitionResult:
    with fitz.open(pdf_path) as doc:
        total_page_count = len(doc)

    native_lines = extract_native_pdf_lines(pdf_path, strip_page_noise=strip_page_noise)
    check_backend = (settings.text_quality_check_backend or "heuristic_placeholder").strip().lower()
    native_report = assess_text_quality(native_lines, total_page_count=total_page_count, backend=check_backend)

    if not native_report.is_malformed:
        return TextAcquisitionResult(
            lines_with_page=native_lines,
            method="native_pdf",
            fallback_used=False,
            native_text_report=native_report,
        )

    ocr_path = locate_ocr_text(pdf_path, settings)
    if ocr_path is None:
        ocr_path = generate_ocr_text_sidecar(pdf_path, settings)
    if ocr_path is not None:
        ocr_lines = load_ocr_lines(ocr_path)
        if ocr_lines:
            return TextAcquisitionResult(
                lines_with_page=ocr_lines,
                method="native_pdf_plus_paddleocr_fallback",
                fallback_used=True,
                native_text_report=native_report,
                ocr_text_path=str(ocr_path),
            )

    return TextAcquisitionResult(
        lines_with_page=native_lines,
        method="native_pdf_malformed_no_ocr_available",
        fallback_used=False,
        native_text_report=native_report,
    )
