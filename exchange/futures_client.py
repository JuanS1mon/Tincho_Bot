"""
binance/futures_client.py
=========================
Wrapper sobre python-binance Client con:
  - Soporte testnet / mainnet (configurado desde settings)
  - Reconexión automática con backoff exponencial
  - Acceso singleton thread-safe
"""
from __future__ import annotations

import time
import threading
from typing import Optional

from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class FuturesClient:
    """Singleton que gestiona la conexión a la API de Binance Futures."""

    _instance: Optional["FuturesClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "FuturesClient":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._client: Optional[Client] = None
        self._connect()

    # ── Conexión ──────────────────────────────────────────────────────────────

    def _connect(self) -> None:
        """Intenta conectar al cliente de Binance. Lanza al primer fallo."""
        logger.info("Conectando a Binance (testnet=%s)...", settings.binance_testnet)
        self._client = Client(
            api_key=settings.binance_api_key,
            api_secret=settings.binance_secret_key,
            testnet=settings.binance_testnet,
        )
        # Verificar conectividad
        self._client.ping()
        logger.info("Conexión a Binance exitosa.")

    def _reconnect(self, max_retries: int = 5) -> None:
        """Reconexión automática con backoff exponencial."""
        for attempt in range(1, max_retries + 1):
            wait = 2 ** attempt
            logger.warning("Reintentando conexión (%d/%d) en %ds...", attempt, max_retries, wait)
            time.sleep(wait)
            try:
                self._connect()
                return
            except Exception as exc:
                error_logger.error("Intento de reconexión %d fallido: %s", attempt, exc)
        raise ConnectionError("No se pudo reconectar a Binance tras %d intentos." % max_retries)

    # ── API pública ───────────────────────────────────────────────────────────

    @property
    def client(self) -> Client:
        if self._client is None:
            self._reconnect()
        return self._client  # type: ignore[return-value]

    def safe_call(self, fn, *args, **kwargs):
        """Ejecuta fn con reintentos en caso de error de red o API."""
        for attempt in range(3):
            try:
                return fn(*args, **kwargs)
            except (BinanceRequestException, ConnectionError) as exc:
                error_logger.error("Error de red en intento %d: %s", attempt + 1, exc)
                self._reconnect()
            except BinanceAPIException as exc:
                error_logger.error("BinanceAPIException: %s", exc)
                raise
        raise RuntimeError("Llamada a Binance fallida tras 3 intentos.")


# Instancia global
futures_client = FuturesClient()
