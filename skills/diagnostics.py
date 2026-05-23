"""
AIRP Diagnostics — lightweight logging for bug tracking.
Uses Python stdlib logging with rotating file handler.
"""
import logging
import logging.handlers
import platform
import sys
import json
from pathlib import Path

LOG_DIR = Path(__file__).parent / "styles" / ".logs"
LOG_FILE = LOG_DIR / "airp.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 3

logger = logging.getLogger("airp")

_initialized = False


def setup_logging(settings_path=None):
    """Initialize the logging system. Call once at server startup."""
    global _initialized
    if _initialized:
        return logger
    _initialized = True

    if settings_path is None:
        settings_path = Path(__file__).parent / "styles" / "settings.json"

    level_str = "warning"
    try:
        if Path(settings_path).exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
                level_str = settings.get("logLevel", "warning").lower()
    except Exception:
        pass

    if level_str == "off":
        logger.addHandler(logging.NullHandler())
        logger.setLevel(logging.CRITICAL + 1)
        return logger

    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
    }
    level = level_map.get(level_str, logging.WARNING)

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s %(name)s.%(funcName)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    logger.addHandler(file_handler)
    logger.setLevel(level)

    logger.info("=== AIRP Diagnostics Started ===")
    logger.info(f"OS: {platform.platform()}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"CWD: {Path.cwd()}")
    logger.info(f"Log level: {level_str}")

    return logger


def get_logger(name=None):
    """Get a child logger for a specific module."""
    if name:
        return logging.getLogger(f"airp.{name}")
    return logger
