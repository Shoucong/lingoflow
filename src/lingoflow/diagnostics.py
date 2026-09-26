"""Explicit bundle self-check using synthetic data and temporary app directories."""

from __future__ import annotations

import gc
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    from lingoflow.config import constants

    with tempfile.TemporaryDirectory(prefix="lingoflow-self-check-") as directory:
        root = Path(directory)
        for name, relative in {
            "APP_SUPPORT_DIR": "support",
            "CONFIG_DIR": "support",
            "CONFIG_FILE": "support/settings.json",
            "CONFIG_BACKUP_FILE": "support/backup.json",
            "LOG_DIR": "logs",
            "LOG_FILE": "logs/app.log",
            "CACHE_DIR": "cache",
            "OCR_CAPTURE_DIR": "cache/ocr",
            "LEGACY_CONFIG_DIR": "legacy",
            "LEGACY_CONFIG_FILE": "legacy/settings.json",
        }.items():
            setattr(constants, name, root / relative)

        from PIL import Image, ImageDraw, ImageFont
        from PyQt6.QtCore import QCoreApplication, QEvent, qVersion
        from PyQt6.QtGui import QTextCursor
        from PyQt6.QtWidgets import QApplication

        from lingoflow.config.settings import AppSettings
        from lingoflow.infrastructure.macos.ocr import OCRService
        from lingoflow.infrastructure.macos.permissions import MacOSPermissionService
        from lingoflow.infrastructure.macos.speech import MacOSSpeechService
        from lingoflow.ui.popup import TranslationPopup
        from lingoflow.ui.settings_dialog import SettingsDialog

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        settings = AppSettings()
        settings.ui.theme = "light"
        evidence = {
            "version": constants.APP_VERSION,
            "python": platform.python_version(),
            "qt_runtime": qVersion(),
            "qt_platform": app.platformName(),
            "frozen": bool(getattr(sys, "frozen", False)),
            "platform": platform.platform(),
            "window_cycles": [],
        }
        assert app.platformName() == "cocoa", "Use the native macOS Qt backend"
        for index in range(30):
            popup = TranslationPopup(settings, window_state_path=root / "window.json")
            popup.show_with_text(
                "The measured value was 12.5 ± 0.3 mm.\nRead without losing your place."
            )
            popup.resize(760, 540)
            popup.start_translation()
            popup.append_translation("测量值为 12.5 ± 0.3 mm。\n阅读时保留当前位置。")
            reader = popup.translation_text.textCursor()
            reader.setPosition(10)
            reader.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
            popup.translation_text.setTextCursor(reader)
            popup.append_translation("\nNew output must leave the selection unchanged.")
            reader = popup.translation_text.textCursor()
            assert (reader.anchor(), reader.position()) == (10, 2)
            popup._install_outside_click_monitor()
            monitors = popup._native_monitor.active_count
            app.processEvents()
            popup.showMinimized()
            app.processEvents()
            assert popup.isMinimized()
            popup.append_translation(" Final text.")
            assert popup.isMinimized()
            popup.showNormal()
            popup.finish_translation()
            app.processEvents()
            if index == 0:
                popup.grab().save(str(output / "reading-window.png"))
            popup.hide()
            popup.append_translation(" Hidden output.")
            assert not popup.isVisible()
            popup.close()
            assert popup._native_monitor.active_count == 0
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            del popup
            gc.collect()
            rss_kib = int(
                subprocess.check_output(
                    ["/bin/ps", "-o", "rss=", "-p", str(os.getpid())],
                    text=True,
                ).strip()
            )
            evidence["window_cycles"].append(
                {"cycle": index + 1, "rss_kib": rss_kib, "registered_monitors": monitors}
            )

        dialog = SettingsDialog(settings)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / "settings.png"))
        assert dialog._build_settings_from_ui() is not None
        dialog.close()

        image = Image.new("RGB", (1300, 190), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
        draw.text((25, 25), "LingoFlow local OCR test", font=font, fill="black")
        draw.text((25, 95), "Keep value 12.5 and citation [12].", font=font, fill="black")
        image_path = root / "synthetic.png"
        image.save(image_path)
        ocr = OCRService(settings)
        started = time.perf_counter()
        recognized = ocr.extract_text(image_path)
        assert recognized.success and "12.5" in recognized.text and "[12]" in recognized.text
        evidence["vision"] = {
            "text": recognized.text,
            "confidence": recognized.confidence,
            "seconds": time.perf_counter() - started,
            "remaining_capture_files": len(list(constants.OCR_CAPTURE_DIR.glob("*"))),
        }
        evidence["permission_preflight"] = [
            {"key": check.key, "state": check.state.value}
            for check in MacOSPermissionService().get_checks()
        ]
        speech = MacOSSpeechService.shared()
        speech.shutdown()
        evidence["completed"] = True
        (output / "self-check.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps({"completed": True, "report": str(output / "self-check.json")}))


if __name__ == "__main__":
    run(Path(sys.argv[1]).resolve())
