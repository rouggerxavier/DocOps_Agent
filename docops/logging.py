"""Logging configuration for DocOps Agent."""

import logging
import sys
from functools import lru_cache


@lru_cache(maxsize=None)
def get_logger(name: str = "docops") -> logging.Logger:
    """Return a configured logger. Cached so the same name always returns the same logger."""
    import os

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
