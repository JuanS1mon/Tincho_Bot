"""
config/logger.py
================
Configura dos loggers:
  - trading_logger  → logs/trading.log + consola
  - error_logger    → logs/errors.log  + consola (nivel ERROR)
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _create_handler(
    path: Path,
    level: int,
    fmt: str,
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
) -> RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt))
    return handler


def _console_handler(level: int, fmt: str) -> logging.StreamHandler:
    h = logging.StreamHandler(sys.stdout)
    h.setLevel(level)
    h.setFormatter(logging.Formatter(fmt))
    return h


_TRADING_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_ERROR_FMT   = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"


def get_trading_logger(name: str = "trading") -> logging.Logger:
    """Logger principal del agente. INFO+ a archivo + consola."""
    from config.settings import settings

    logger = logging.getLogger(name)
    if logger.handlers:          # ya configurado
        return logger

    logger.setLevel(logging.DEBUG)
    logger.addHandler(_create_handler(settings.logs_dir / "trading.log", logging.DEBUG, _TRADING_FMT))
    logger.addHandler(_console_handler(logging.INFO, _TRADING_FMT))
    logger.propagate = False
    return logger


def get_error_logger(name: str = "errors") -> logging.Logger:
    """Logger de errores. ERROR+ a archivo + consola."""
    from config.settings import settings

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.ERROR)
    logger.addHandler(_create_handler(settings.logs_dir / "errors.log", logging.ERROR, _ERROR_FMT))
    logger.addHandler(_console_handler(logging.ERROR, _ERROR_FMT))
    logger.propagate = False
    return logger


# Loggers pre-instanciados para importación directa
trading_logger = get_trading_logger()
error_logger = get_error_logger()
