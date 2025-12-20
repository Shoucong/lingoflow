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

from lingoflow.config.constants import APP_NAME, LOG_DIR, LOG_FILE_NAME

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
    