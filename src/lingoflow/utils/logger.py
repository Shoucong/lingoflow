"""
Logging configuration for LingoFlow. 

Provides a centralized logger setup with both console and file output. 
Usage: 
    from lingoflow.utils.logger import get_logger

    logger = get_logger(__name__)
    logger.info("Application started.")
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from lingoflow.config.constants import APP_NAME, LOG_DIR, LOG_FILE

# ===========================================================
# Configuration
# ===========================================================

DEFAULT_LOG_LEVEL = logging.INFO
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_SIZE = 5 * 1024 * 1024 # 5MB
BACKUP_COUNT = 3 # Keep 3 old log files

# Track if logging has been initialized
_initialized = False

# ===========================================================
# Setup Functions
# ==========================================================

def setup_logging(level: int = DEFAULT_LOG_LEVEL, console: bool = True) -> None:
    """
    Initialize the logging system.

    Shoud be called once at application startup. 

    Args: 
        level (int): Logging level (e.g., logging.DEBUG, logging.INFO)
        console (bool): Whether to also output to console
    """
    global _initialized

    if _initialized:
        return
    
    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Get root logger for the app
    root_logger = logging.getLogger(APP_NAME.lower())
    root_logger.setLevel(level)
    
    # Prevent propagation to avoid duplicate logs
    root_logger.propagate = False

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Create formatter
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    # File handler with rotation
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_LOG_SIZE,
        backupCount=BACKUP_COUNT,
        encoding='utf-8', 
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    _initialized = True
    root_logger.debug("Logging initialized")

def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module. 

    Args: 
        name: Usually __name__ of the calling module
    
    Returns:
        Configured logger instance
    
    Example: 
        logger = get_logger(__name__)
        logger.info("Something happened")
    """
    if not _initialized:
        setup_logging()
    
    # Create child logger under our app's namespace
    # This ensures all our loggers inherit the same configuration
    if name.startswith("lingoflow"):
        logger_name = name
    else:
        # Add our prefix for consistency
        logger_name = f"{APP_NAME.lower()}.{name}"
    
    return logging.getLogger(logger_name)

def set_log_level(level: int) -> None:
    """
    Change the log level at runtime. 

    Args:
        level: New logging level (e.g., logging.DEBUG)
    """
    root_logger = logging.getLogger(APP_NAME.lower())
    root_logger.setLevel(level)
    for handler in root_logger.handlers:
        handler.setLevel(level)

# ===========================================================
# Convenience Functions
# ==========================================================
def enable_debug() -> None:
    """Enable debug logging."""
    set_log_level(logging.DEBUG)

def disable_console() -> None:
    """Remove console handler, keep only file logging."""
    root_logger = logging.getLogger(APP_NAME.lower())
    root_logger.handlers = [
        h for h in root_logger.handlers
        if not isinstance(h, logging.StreamHandler) or h.stream != sys.stdout
    ]