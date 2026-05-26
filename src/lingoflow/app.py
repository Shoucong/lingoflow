"""
LingoFlow Application Entry Point.

This module initializes and runs the LingoFlow application.
"""

import os
import platform
import sys
from importlib.util import find_spec
from typing import NoReturn

# Suppress Qt ICC profile warnings on macOS (harmless but noisy)
os.environ["QT_LOGGING_RULES"] = "qt.gui.icc=false"

from PyQt6.QtWidgets import QApplication

from lingoflow.config.constants import (
    APP_NAME,
    APP_VERSION,
    SINGLE_INSTANCE_LOCK,
    SINGLE_INSTANCE_SOCKET,
)
from lingoflow.utils.logger import get_logger, setup_logging


def configure_macos() -> None:
    """Configure macOS-specific settings."""
    if platform.system() != "Darwin":
        return

    # Hide dock icon (we're a menu bar app)
    try:
        from Foundation import NSBundle

        bundle = NSBundle.mainBundle()
        info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
        if info:
            info["LSUIElement"] = "1"
    except ImportError:
        # PyObjC not fully available, skip
        pass


def check_dependencies() -> bool:
    """
    Check that required dependencies are available.

    Returns:
        True if all dependencies are satisfied
    """
    logger = get_logger(__name__)
    all_good = True

    if platform.system() != "Darwin":
        logger.error("LingoFlow currently requires macOS.")
        all_good = False

    required_modules = [
        ("PyQt6", "PyQt6.QtWidgets", "pip install PyQt6"),
        ("Quartz", "Quartz", "pip install pyobjc-framework-Quartz"),
        ("httpx", "httpx", "pip install httpx"),
        ("Pillow", "PIL.Image", "pip install Pillow"),
    ]
    for label, module_name, install_command in required_modules:
        if find_spec(module_name) is None:
            logger.error(f"{label} not found. Install with: {install_command}")
            all_good = False
        else:
            logger.debug(f"{label}: OK")

    # Check macOS Vision (optional but recommended on macOS)
    if platform.system() == "Darwin":
        if find_spec("Vision") is None:
            logger.warning(
                "Apple Vision not available. Install with: pip install pyobjc-framework-Vision"
            )
            # Not a hard requirement, OCR just won't work
        else:
            logger.debug("Apple Vision: OK")

    return all_good


def show_permission_help() -> None:
    """Show help for macOS permission requirements."""
    if platform.system() != "Darwin":
        return

    logger = get_logger(__name__)
    logger.info(
        "\n"
        "=== macOS Permissions Required ===\n"
        "LingoFlow needs the following permissions:\n"
        "\n"
        "1. Input Monitoring (for global hotkeys)\n"
        "   System Settings → Privacy & Security → Input Monitoring\n"
        "\n"
        "2. Accessibility (for getting selected text)\n"
        "   System Settings → Privacy & Security → Accessibility\n"
        "\n"
        "3. Screen Recording (for OCR screenshots)\n"
        "   System Settings → Privacy & Security → Screen Recording\n"
        "\n"
        "After granting permissions, restart LingoFlow.\n"
        "=================================="
    )


def main() -> NoReturn:
    """
    Main entry point for LingoFlow.
    """
    # Initialize logging first
    setup_logging()
    logger = get_logger(__name__)

    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    logger.info(f"Platform: {platform.system()} {platform.release()}")
    logger.info(f"Python: {platform.python_version()}")

    # Check dependencies
    if not check_dependencies():
        logger.error("Missing dependencies. Please install them and try again.")
        sys.exit(1)

    # Configure macOS
    configure_macos()

    # Create Qt application
    app = QApplication(sys.argv)

    # Configure application
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("LingoFlow")
    app.setOrganizationDomain("lingoflow.app")

    # Don't quit when last window closes (we're a tray app)
    app.setQuitOnLastWindowClosed(False)

    from lingoflow.infrastructure.single_instance import SingleInstanceGuard

    single_instance = SingleInstanceGuard(
        str(SINGLE_INSTANCE_LOCK),
        str(SINGLE_INSTANCE_SOCKET),
    )
    if not single_instance.acquire():
        single_instance.notify_existing_instance()
        logger.info("Another LingoFlow instance is already running; exiting")
        sys.exit(0)
    single_instance.listen()

    # Import here to avoid circular imports
    from lingoflow.ui.main_window import MainController

    # Create main controller
    controller = MainController()
    single_instance.activate_requested.connect(controller.handle_external_launch)
    controller.start()

    logger.info("Application started, entering event loop")

    # Run the event loop
    exit_code = app.exec()
    single_instance.release()

    logger.info(f"Application exiting with code {exit_code}")
    sys.exit(exit_code)


def run_cli() -> None:
    """
    Alternative entry point for CLI testing.
    """
    import argparse

    setup_logging()

    parser = argparse.ArgumentParser(description=f"{APP_NAME} - Ollama-powered translation app")
    parser.add_argument("--version", "-v", action="version", version=f"{APP_NAME} {APP_VERSION}")
    parser.add_argument("--test-translate", metavar="TEXT", help="Test translation with given text")
    parser.add_argument(
        "--test-ocr", action="store_true", help="Test OCR with interactive screen capture"
    )
    parser.add_argument("--list-models", action="store_true", help="List available Ollama models")
    parser.add_argument(
        "--check", action="store_true", help="Check dependencies and Ollama connection"
    )

    args = parser.parse_args()

    if args.check:
        print(f"{APP_NAME} v{APP_VERSION}")
        print()
        print("Checking dependencies...")
        check_dependencies()
        print()
        print("Checking Ollama connection...")
        from lingoflow.infrastructure.ollama_client import OllamaClient

        client = OllamaClient()
        if client.is_available():
            print("✓ Ollama is running")
            models = client.list_models()
            print(f"✓ Found {len(models)} models")
        else:
            print("✗ Ollama is not running")
            print("  Start with: ollama serve")
        return

    if args.list_models:
        from lingoflow.infrastructure.ollama_client import OllamaClient

        client = OllamaClient()
        try:
            models = client.list_models()
            print("Available models:")
            for m in models:
                size_gb = m.size / (1024**3)
                print(f"  - {m.name} ({size_gb:.1f} GB)")
        except Exception as e:
            print(f"Error: {e}")
        return

    if args.test_translate:
        from lingoflow.core.translator import TranslationService

        service = TranslationService()
        print(f"Translating: {args.test_translate}")
        print("Result: ", end="", flush=True)
        for chunk in service.translate_stream(args.test_translate):
            print(chunk, end="", flush=True)
        print()
        return

    if args.test_ocr:
        from lingoflow.core.ocr import OCRService

        service = OCRService()
        print("Select a screen region...")
        result = service.capture_and_extract()
        if result.success:
            print(f"Extracted text:\n{result.text}")
        else:
            print(f"Error: {result.error_message}")
        return

    # No arguments, run the full app
    main()


if __name__ == "__main__":
    run_cli()
