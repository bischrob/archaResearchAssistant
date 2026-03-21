from pathlib import Path

from src.rag.config import Settings
from src.rag.text_acquisition import acquire_pdf_text, assess_text_quality


def test_assess_text_quality_marks_obviously_bad_native_text() -> None:
    report = assess_text_quality(
        [(1, "\x01\x02\x03 \x00 \x00"), (2, "12 34 56")],
        total_page_count=4,
        backend="heuristic_placeholder",
    )

    assert report.is_malformed is True
    assert "native_text_too_short" in report.reason


def test_acquire_pdf_text_prefers_native_when_quality_is_acceptable(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "good.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")

    monkeypatch.setattr(
        "src.rag.text_acquisition.extract_native_pdf_lines",
        lambda *_args, **_kwargs: [
            (
                1,
                "This is readable native PDF text with enough alphabetic content to pass the conservative malformed-text gate. "
                * 4,
            )
        ],
    )
    monkeypatch.setattr("src.rag.text_acquisition.locate_ocr_text", lambda *_args, **_kwargs: None)

    result = acquire_pdf_text(pdf_path, settings=Settings(paddleocr_auto_generate_missing_text=False))

    assert result.method == "native_pdf"
    assert result.fallback_used is False
    assert result.native_text_report.is_malformed is False


def test_acquire_pdf_text_falls_back_to_paddleocr_when_native_text_is_bad(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "bad.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\n")
    ocr_path = tmp_path / "bad.txt"
    ocr_path.write_text("Recovered OCR line one\nRecovered OCR line two\n", encoding="utf-8")

    monkeypatch.setattr(
        "src.rag.text_acquisition.extract_native_pdf_lines",
        lambda *_args, **_kwargs: [(1, "\x00 \x01 12 34"), (2, "\x02 \x03")],
    )
    monkeypatch.setattr("src.rag.text_acquisition.locate_ocr_text", lambda *_args, **_kwargs: ocr_path)

    result = acquire_pdf_text(pdf_path, settings=Settings(paddleocr_auto_generate_missing_text=False))

    assert result.method == "native_pdf_plus_paddleocr_fallback"
    assert result.fallback_used is True
    assert result.ocr_text_path == str(ocr_path)
    assert [line for _, line in result.lines_with_page] == ["Recovered OCR line one", "Recovered OCR line two"]
