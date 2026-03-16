"""
app/agent_runner.py
====================
Inicia el agente de trading y la API HTTP en threads paralelos.
Maneja el ciclo de vida completo con graceful shutdown.
"""
from __future__ import annotations

import signal
import threading
import sys

import uvicorn

from agent.trading_agent import TradingAgent
from agent.marquitos_agent import MarquitosAgent, marquitos_agent
from api.status_api import app as fastapi_app, set_agent, set_runner
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class AgentRunner:
    """Orquesta el inicio del agente y la API en paralelo."""

    def __init__(self, dry_run: bool = True, interval_override: int | None = None, force_ai: bool = False, tryhard: bool = False) -> None:
        self.dry_run = dry_run
        self.agent = TradingAgent(dry_run=dry_run, interval_override=interval_override, force_ai=force_ai, tryhard=tryhard)
        marquitos_agent.dry_run = dry_run
        self._api_thread: threading.Thread | None = None
        self._agent_thread: threading.Thread | None = None
        self._marquitos_thread: threading.Thread | None = None
        self._marquitos_active: bool = False

    def run(self) -> None:
        """
        Inicia:
          - API HTTP en thread daemon
          - Agente de trading en thread principal

        Captura SIGINT / SIGTERM para apagado limpio.
        """
        # Registrar manejadores de señal del OS
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Inyectar agente en la API
        set_agent(self.agent)
        set_runner(self)

        # 1. Iniciar API en thread daemon
        self._start_api()

        # 2. (NO iniciar Marquitos automáticamente)

        # 3. Iniciar agente principal en thread separado (no daemon) para poder hacer join
        logger.info("Iniciando agente de trading (dry_run=%s)...", self.dry_run)
        self._agent_thread = threading.Thread(
            target=self._run_agent,
            name="TradingAgentThread",
            daemon=False,
        )
        self._agent_thread.start()

        # Mantener el proceso vivo esperando al agente
        try:
            self._agent_thread.join()
        except KeyboardInterrupt:
            self._shutdown()

    def start_marquitos(self) -> None:
        """Activa Marquitos manualmente (si no está activo)."""
        if self._marquitos_active:
            logger.info("Marquitos ya está activo.")
            return
        logger.info("Activando Marquitos (scalper, dry_run=%s)...", self.dry_run)
        self._marquitos_thread = threading.Thread(
            target=marquitos_agent.start,
            name="MarquitosThread",
            daemon=True,
        )
        self._marquitos_thread.start()
        self._marquitos_active = True

    def stop_marquitos(self) -> None:
        """Detiene Marquitos manualmente (si está activo)."""
        if not self._marquitos_active:
            logger.info("Marquitos ya está detenido.")
            return
        logger.info("Deteniendo Marquitos...")
        marquitos_agent.stop()
        self._marquitos_active = False

    def _run_agent(self) -> None:
        try:
            self.agent.start()
        except Exception as exc:
            error_logger.error("Error fatal en el agente: %s", exc, exc_info=True)
            self._shutdown()

    def _start_api(self) -> None:
        """Inicia uvicorn en un thread daemon."""
        config = uvicorn.Config(
            app=fastapi_app,
            host=settings.api_host,
            port=settings.api_port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)

        self._api_thread = threading.Thread(
            target=server.run,
            name="APIThread",
            daemon=True,
        )
        self._api_thread.start()
        logger.info(
            "API HTTP iniciada en http://%s:%d",
            settings.api_host, settings.api_port,
        )

    def _handle_shutdown(self, signum, frame) -> None:
        """Manejador de señal OS para shutdown graceful."""
        logger.info("Señal de apagado recibida (%s).", signum)
        self._shutdown()

    def _shutdown(self) -> None:
        logger.info("Apagando sistema...")
        self.agent.stop()
        if self._marquitos_active:
            marquitos_agent.stop()
        # La API se cierra sola al terminar el proceso (daemon thread)
        sys.exit(0)
