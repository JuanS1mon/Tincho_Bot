"""
App - Scheduler
=================
Loop principal del bot de trading.
Ejecuta el flujo completo cada EXECUTION_INTERVAL_MINUTES (default 15 min).
Maneja errores con logging + continuación del loop.
"""

import sys
import time
import signal
from datetime import datetime
from pathlib import Path

# Agregar raíz del proyecto al path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from config.logger import setup_logging, get_logger
from app.main import TradingBot

logger = get_logger(__name__)

# Flag global para shutdown graceful
_shutdown_requested = False


def _signal_handler(signum, frame):
    """Handler para señales del sistema (Ctrl+C)."""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n⚠️  Shutdown solicitado. Finalizando ciclo actual...")
    logger.info(f"Señal {signum} recibida. Shutdown solicitado.")


def run_scheduler():
    """
    Loop principal del scheduler.
    Ejecuta el bot cada EXECUTION_INTERVAL_MINUTES minutos.
    """
    # Registrar handler para Ctrl+C
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Inicializar logging
    setup_logging()

    interval_minutes = settings.EXECUTION_INTERVAL_MINUTES
    interval_seconds = interval_minutes * 60

    logger.info(f"🚀 Scheduler iniciado. Intervalo: cada {interval_minutes} minutos")

    # Inicializar el bot
    bot = TradingBot()

    try:
        while not _shutdown_requested:
            cycle_start = time.time()

            try:
                logger.info(
                    f"\n⏰ Siguiente ejecución: "
                    f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
                bot.run_cycle()

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt recibido")
                break

            except Exception as e:
                logger.error(f"❌ Error en ciclo del scheduler: {e}")
                logger.error("El scheduler continuará en el próximo intervalo")

            # Calcular tiempo de espera
            cycle_duration = time.time() - cycle_start
            wait_time = max(0, interval_seconds - cycle_duration)

            if _shutdown_requested:
                break

            if wait_time > 0:
                logger.info(
                    f"💤 Esperando {wait_time:.0f}s hasta el próximo ciclo "
                    f"(ciclo anterior: {cycle_duration:.1f}s)"
                )

                # Esperar en intervalos cortos para poder responder a shutdown
                waited = 0
                while waited < wait_time and not _shutdown_requested:
                    sleep_chunk = min(10, wait_time - waited)
                    time.sleep(sleep_chunk)
                    waited += sleep_chunk

    except Exception as e:
        logger.error(f"Error fatal en scheduler: {e}")

    finally:
        bot.shutdown()
        logger.info("📛 Scheduler finalizado")


if __name__ == "__main__":
    run_scheduler()
