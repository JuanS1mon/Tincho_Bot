"""
Config - Logger
================
Sistema de logging centralizado con 3 handlers rotativos:
  - trading.log  → operaciones generales del bot
  - errors.log   → errores y excepciones
  - ai.log       → comunicación con la IA
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.settings import settings, BASE_DIR

# Directorio de logs
LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Formato estándar
LOG_FORMAT = "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Tamaño máximo por archivo (5 MB) y backups
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def _create_rotating_handler(
    filename: str, level: int = logging.DEBUG
) -> RotatingFileHandler:
    """Crea un handler rotativo para un archivo de log."""
    handler = RotatingFileHandler(
        LOGS_DIR / filename,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    return handler


def setup_logging() -> None:
    """Configura el sistema de logging global del bot."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # --- Root logger ---
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Limpiar handlers previos (evita duplicados en recargas)
    root_logger.handlers.clear()

    # --- Console handler ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(console_handler)

    # --- Trading log (todo nivel INFO+) ---
    trading_handler = _create_rotating_handler("trading.log", logging.INFO)
    root_logger.addHandler(trading_handler)

    # --- Errors log (solo ERROR+) ---
    error_handler = _create_rotating_handler("errors.log", logging.ERROR)
    root_logger.addHandler(error_handler)

    # --- AI log (logger específico) ---
    ai_logger = logging.getLogger("ai")
    ai_logger.setLevel(logging.DEBUG)
    ai_handler = _create_rotating_handler("ai.log", logging.DEBUG)
    ai_logger.addHandler(ai_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger con nombre específico.
    
    Uso:
        from config.logger import get_logger
        logger = get_logger(__name__)
        logger.info("Mensaje")
    """
    return logging.getLogger(name)
