#!/usr/bin/env python3
"""Run regression tests with isolated app data and an explicit Qt backend."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qt-platform", choices=("offscreen", "cocoa"), default="offscreen")
    options, test_args = parser.parse_known_args()
    os.environ["QT_QPA_PLATFORM"] = options.qt_platform
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    # Allow the build interpreter to reuse test-only tools from the project venv.
    for site in (root / ".venv" / "lib").glob("python*/site-packages"):
        if str(site) not in sys.path:
            sys.path.append(str(site))

    from lingoflow.config import constants

    with tempfile.TemporaryDirectory(prefix="lingoflow-checks-") as directory:
        data = Path(directory)
        paths = {
            "APP_SUPPORT_DIR": "support",
            "CONFIG_DIR": "support",
            "CONFIG_FILE": "support/settings.json",
            "CONFIG_BACKUP_FILE": "support/settings.backup.json",
            "LOG_DIR": "logs",
            "LOG_FILE": "logs/lingoflow.log",
            "CACHE_DIR": "cache",
            "OCR_CAPTURE_DIR": "cache/ocr",
            "LEGACY_CONFIG_DIR": "legacy",
            "LEGACY_CONFIG_FILE": "legacy/settings.json",
            "SINGLE_INSTANCE_LOCK": "support/instance.lock",
            "SINGLE_INSTANCE_SOCKET": "support/instance.socket",
        }
        for name, relative in paths.items():
            setattr(constants, name, data / relative)

        import pytest

        return pytest.main(["-q", "-p", "no:cacheprovider", *test_args])


if __name__ == "__main__":
    raise SystemExit(main())
