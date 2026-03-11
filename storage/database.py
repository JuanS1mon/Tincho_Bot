"""
storage/database.py
====================
Conexión singleton a MongoDB usando pymongo.
Crea los índices necesarios al inicializar.
"""
from __future__ import annotations

import threading
from typing import Optional

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database

from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class DatabaseManager:
    """Singleton de conexión a MongoDB."""

    _instance: Optional["DatabaseManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._client: Optional[MongoClient] = None
        self._db: Optional[Database] = None
        self._connect()

    def _connect(self) -> None:
        try:
            logger.info("Conectando a MongoDB: %s", settings.mongo_uri)
            self._client = MongoClient(
                settings.mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            # Verificar conexión
            self._client.admin.command("ping")
            self._db = self._client[settings.mongo_db_name]
            self._create_indexes()
            logger.info("MongoDB conectado: db=%s", settings.mongo_db_name)
        except Exception as exc:
            error_logger.error("Error conectando a MongoDB: %s", exc)
            raise

    def _create_indexes(self) -> None:
        """Crea índices para optimizar las consultas más frecuentes."""
        try:
            db = self._db

            # Colección: trades
            db["trades"].create_index([("symbol", ASCENDING), ("timestamp", DESCENDING)])
            db["trades"].create_index([("timestamp", DESCENDING)])

            # Colección: market_snapshots
            db["market_snapshots"].create_index([("symbol", ASCENDING), ("timestamp", DESCENDING)])

            # Colección: agent_states
            db["agent_states"].create_index([("timestamp", DESCENDING)])

            logger.debug("Índices MongoDB creados/verificados.")
        except Exception as exc:
            error_logger.error("Error creando índices MongoDB: %s", exc)

    @property
    def db(self) -> Database:
        if self._db is None:
            self._connect()
        return self._db  # type: ignore[return-value]

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("Conexión MongoDB cerrada.")


# Singleton global
db_manager = DatabaseManager()
