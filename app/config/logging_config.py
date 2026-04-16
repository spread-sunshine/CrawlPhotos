# -*- coding: utf-8 -*-
"""
Logging configuration module.
日志配置模块 - 结构化日志、文件轮转、级别控制.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

# Default log directory
DEFAULT_LOG_DIR = Path("logs")


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[Path] = None,
    max_file_size_mb: int = 50,
    retention_days: int = 90,
    log_prefix: str = "app",
) -> logging.Logger:
    """
    Configure application-wide logging.

    Sets up:
    - Console handler with colored output.
    - File handler with rotation.
    - Error-specific file handler.

    Args:
        log_level: Logging level string (DEBUG/INFO/WARN/ERROR).
        log_dir: Directory for log files.
        max_file_size_mb: Max size per log file in MB.
        retention_days: Days to retain old logs.
        log_prefix: Prefix for log filenames.

    Returns:
        Configured root logger instance.
    """
    logger = logging.getLogger("baby_photos")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid duplicate handlers when called multiple times
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | %(name)s | "
            "%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handlers (only if log_dir specified)
    log_dir = log_dir or DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)

    max_bytes = max_file_size_mb * 1024 * 1024

    # Main log file
    main_file = log_dir / f"{log_prefix}_{_today_str()}.log"
    file_handler = RotatingFileHandler(
        main_file,
        maxBytes=max_bytes,
        backupCount=retention_days,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Error-only log file
    error_file = log_dir / f"{log_prefix}_error_{_today_str()}.log"
    error_handler = RotatingFileHandler(
        error_file,
        maxBytes=max_bytes,
        backupCount=retention_days,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    # Suppress noisy third-party loggers
    _suppress_noisy_loggers(logger)

    logger.info("Logging initialized: level=%s, dir=%s", log_level, log_dir)
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a named child logger.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Logger instance.
    """
    return logging.getLogger(f"baby_photos.{name}")


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD string."""
    from datetime import date
    return date.today().isoformat()


def _suppress_noisy_loggers(root_logger: logging.Logger) -> None:
    """Set third-party loggers to WARNING or higher."""
    noisy_names = [
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "PIL",
        "asyncio",
    ]
    for name in noisy_names:
        logging.getLogger(name).setLevel(logging.WARNING)
