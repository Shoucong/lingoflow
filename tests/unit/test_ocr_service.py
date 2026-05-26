from __future__ import annotations

from pathlib import Path

from lingoflow.config.settings import AppSettings
from lingoflow.core.ocr import OCRService


def make_service(keep_captures: bool = False) -> OCRService:
    settings = AppSettings()
    settings.privacy.keep_ocr_captures = keep_captures
    return OCRService(settings)


def test_cleanup_capture_deletes_only_managed_capture(
    isolated_ocr_capture_dir: Path,
    tmp_path: Path,
) -> None:
    service = make_service()
    managed = isolated_ocr_capture_dir / "capture-managed.png"
    unmanaged = tmp_path / "capture-unmanaged.png"
    managed.write_bytes(b"image")
    unmanaged.write_bytes(b"image")

    assert service.cleanup_capture(managed) is True
    assert service.cleanup_capture(unmanaged) is False
    assert not managed.exists()
    assert unmanaged.exists()


def test_cleanup_capture_keeps_file_when_retention_enabled(
    isolated_ocr_capture_dir: Path,
) -> None:
    service = make_service(keep_captures=True)
    managed = isolated_ocr_capture_dir / "capture-kept.png"
    managed.write_bytes(b"image")

    assert service.cleanup_capture(managed) is False
    assert managed.exists()


def test_cleanup_stale_captures_removes_managed_pngs_only(
    isolated_ocr_capture_dir: Path,
) -> None:
    service = make_service()
    stale = isolated_ocr_capture_dir / "capture-stale.png"
    unrelated = isolated_ocr_capture_dir / "notes.txt"
    stale.write_bytes(b"image")
    unrelated.write_text("leave me", encoding="utf-8")

    service.cleanup_stale_captures()

    assert not stale.exists()
    assert unrelated.exists()


def test_new_capture_path_is_unique_and_managed(isolated_ocr_capture_dir: Path) -> None:
    service = make_service()

    first = service._new_capture_path()
    second = service._new_capture_path()

    assert first != second
    assert first.parent == isolated_ocr_capture_dir
    assert first.name.startswith("capture-")
    assert first.suffix == ".png"
