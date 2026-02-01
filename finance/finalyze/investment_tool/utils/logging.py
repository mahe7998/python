"""Logging configuration for the investment tool."""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def setup_logging(
    log_file: Optional[Path] = None,
    level: str = "INFO",
    max_size_mb: int = 10,
    backup_count: int = 5,
) -> None:
    """
    Configure application logging.

    Args:
        log_file: Path to log file (optional)
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        max_size_mb: Maximum log file size in MB before rotation
        backup_count: Number of backup files to keep
    """
    logger.remove()

    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=level,
        colorize=True,
    )

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            str(log_file),
            format=log_format,
            level=level,
            rotation=f"{max_size_mb} MB",
            retention=backup_count,
            compression="zip",
        )
        logger.info(f"Logging to file: {log_file}")


def get_logger(name: str) -> "logger":
    """
    Get a logger instance for a module.

    Args:
        name: Module name

    Returns:
        Logger instance
    """
    return logger.bind(name=name)
