from __future__ import annotations

import sys
import threading
import time
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


def test_cancelling_capture_terminates_its_process(isolated_ocr_capture_dir: Path) -> None:
    service = make_service()
    results = []
    worker = threading.Thread(
        target=lambda: results.append(
            service._run_capture(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                timeout=5,
            )
        )
    )
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while service._capture_process is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert service._capture_process is not None
        service.cancel()
        worker.join(2)
        assert not worker.is_alive()
        assert results[0].returncode == -1
        assert service._capture_process is None
    finally:
        service.cancel()
        worker.join(3)


def test_image_enhancement_is_applied_and_temporary_derivative_is_removed(
    isolated_ocr_capture_dir,
    tmp_path,
    monkeypatch,
):
    from PIL import Image

    from lingoflow.core.ocr import OCRResult

    source = tmp_path / "original.png"
    Image.new("RGB", (100, 100), "white").save(source)
    service = make_service()
    paths = []

    def recognize(path):
        paths.append(path)
        assert path.exists()
        with Image.open(path) as image:
            assert image.width >= 300
        return OCRResult("recognized")

    monkeypatch.setattr(service, "_extract_text_apple_vision", recognize)
    result = service.extract_text(source)
    assert result.text == "recognized"
    assert result.source_image_path == str(source)
    assert paths[0] != source and not paths[0].exists()
    assert source.exists()
