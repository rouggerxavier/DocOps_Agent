"""Logging configuration for DocOps Agent."""

import logging
import sys
from functools import lru_cache

from docops.observability import get_correlation_id


class _CorrelationIdFilter(logging.Filter):
    """Inject correlation id from contextvars into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id(default="-")
        return True


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
        handler.addFilter(_CorrelationIdFilter())
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [cid=%(correlation_id)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(level)
    return logger
