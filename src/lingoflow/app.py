"""
LingoFlow Application Entry Point.

This module initializes and runs the LingoFlow application.
"""

import sys
import os
import platform
from typing import NoReturn

# Suppress Qt ICC profile warnings on macOS (harmless but noisy)
os.environ["QT_LOGGING_RULES"] = "qt.gui.icc=false"

from PyQt6.QtWidgets import QApplication

from lingoflow.config.constants import APP_NAME, APP_VERSION
from lingoflow.utils.logger import setup_logging, get_logger


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
    
    # Check PyQt6
    try:
        from PyQt6.QtWidgets import QApplication
        logger.debug("PyQt6: OK")
    except ImportError:
        logger.error("PyQt6 not found. Install with: pip install PyQt6")
        all_good = False
    
    # Check pynput
    try:
        from pynput import keyboard
        logger.debug("pynput: OK")
    except ImportError:
        logger.error("pynput not found. Install with: pip install pynput")
        all_good = False
    
    # Check httpx
    try:
        import httpx
        logger.debug("httpx: OK")
    except ImportError:
        logger.error("httpx not found. Install with: pip install httpx")
        all_good = False
    
    # Check Pillow
    try:
        from PIL import Image
        logger.debug("Pillow: OK")
    except ImportError:
        logger.error("Pillow not found. Install with: pip install Pillow")
        all_good = False
    
    # Check macOS Vision (optional but recommended on macOS)
    if platform.system() == "Darwin":
        try:
            import Vision
            logger.debug("Apple Vision: OK")
        except ImportError:
            logger.warning(
                "Apple Vision not available. "
                "Install with: pip install pyobjc-framework-Vision"
            )
            # Not a hard requirement, OCR just won't work
    
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
    
    # Show permission help on first run (macOS)
    show_permission_help()
    
    # Create Qt application
    app = QApplication(sys.argv)
    
    # Configure application
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("LingoFlow")
    app.setOrganizationDomain("lingoflow.app")
    
    # Don't quit when last window closes (we're a tray app)
    app.setQuitOnLastWindowClosed(False)
    
    # Import here to avoid circular imports
    from lingoflow.ui.main_window import MainController
    
    # Create main controller
    controller = MainController()
    controller.start()
    
    logger.info("Application started, entering event loop")
    
    # Run the event loop
    exit_code = app.exec()
    
    logger.info(f"Application exiting with code {exit_code}")
    sys.exit(exit_code)


def run_cli() -> None:
    """
    Alternative entry point for CLI testing.
    """
    import argparse
    
    setup_logging()
    logger = get_logger(__name__)
    
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - Ollama-powered translation app"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"{APP_NAME} {APP_VERSION}"
    )
    parser.add_argument(
        "--test-translate",
        metavar="TEXT",
        help="Test translation with given text"
    )
    parser.add_argument(
        "--test-ocr",
        action="store_true",
        help="Test OCR with interactive screen capture"
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="List available Ollama models"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check dependencies and Ollama connection"
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
                size_gb = m.size / (1024 ** 3)
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