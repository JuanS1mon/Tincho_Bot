"""
app/main.py
============
Entry point principal del sistema Tincho Bot.

Uso:
  python app/main.py                  # inicia el agente (modo testnet por defecto)
  python app/main.py --live           # modo real (requiere claves de mainnet)
  python app/main.py --dry-run        # simulación sin ejecutar trades
  python app/main.py --no-api         # sin API HTTP
  python app/main.py --check-config   # verifica la configuración y sale

El directorio de trabajo siempre debe ser la raíz del proyecto:
  cd c:\\Tincho-bot
  python app/main.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Asegurar que la raíz del proyecto esté en sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Forzar UTF-8 en stdout para que los caracteres especiales funcionen en Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tincho Bot — Agente Autónomo de Trading de Criptomonedas",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python app/main.py                    Inicia en testnet (dry-run por defecto)
  python app/main.py --live             Usa mainnet y ejecuta trades reales
  python app/main.py --dry-run          Nunca ejecuta trades, solo simula
  python app/main.py --check-config     Imprime configuración y sale
        """,
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Modo live: ejecuta trades reales en Binance Futures",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        help="Simula trades sin enviarlos a Binance (por defecto en testnet)",
    )
    parser.add_argument(
        "--no-api",
        action="store_true",
        dest="no_api",
        help="No iniciar la API HTTP (útil para debugging)",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        dest="check_config",
        help="Imprime la configuración cargada y sale",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=None,
        dest="interval",
        metavar="SEGUNDOS",
        help="Override del intervalo de análisis en segundos (ej. --interval 60 para simulaciones)",
    )
    parser.add_argument(
        "--force-ai",
        action="store_true",
        dest="force_ai",
        help="Fuerza la consulta a la IA en el primer ciclo aunque no haya señal (útil para pruebas)",
    )
    return parser.parse_args()


def check_config() -> None:
    """Imprime la configuración cargada y valida valores críticos."""
    from config.settings import settings

    print("\n" + "=" * 50)
    print("  Tincho Bot — Verificación de Configuración")
    print("=" * 50)
    print(f"  Binance Testnet : {settings.binance_testnet}")
    print(f"  API Key set     : {'✓' if settings.binance_api_key else '✗ VACÍO'}")
    print(f"  Secret Key set  : {'✓' if settings.binance_secret_key else '✗ VACÍO'}")
    print(f"  AI Provider     : {settings.ai_provider}")
    print(f"  AI Model        : {settings.ai_model}")
    print(f"  AI API Key set  : {'✓' if settings.ai_api_key else '✗ VACÍO'}")
    print(f"  Símbolos        : {', '.join(settings.symbols)}")
    print(f"  Capital inicial : {settings.initial_capital} USDT")
    print(f"  Leverage        : {settings.leverage}x")
    print(f"  Max capital/op  : {settings.max_capital_per_trade * 100:.0f}%")
    print(f"  Stop Loss       : {settings.stop_loss * 100:.1f}%")
    print(f"  Take Profit     : {settings.take_profit * 100:.1f}%")
    print(f"  Timeframe       : {settings.timeframe}")
    print(f"  Intervalo análi : {settings.analysis_interval_seconds}s")
    print(f"  MongoDB URI     : {settings.mongo_uri}")
    print(f"  API HTTP        : http://{settings.api_host}:{settings.api_port}")
    print("=" * 50 + "\n")

    warnings = []
    if not settings.binance_api_key:
        warnings.append("BINANCE_API_KEY no configurada")
    if not settings.ai_api_key:
        warnings.append("AI_API_KEY no configurada")
    if not settings.binance_testnet:
        warnings.append("⚠  MODO MAINNET ACTIVO — se usará dinero real")

    if warnings:
        print("Advertencias:")
        for w in warnings:
            print(f"  • {w}")
        print()


def main() -> None:
    args = parse_args()

    if args.check_config:
        check_config()
        sys.exit(0)

    # Mostrar configuración al inicio
    check_config()

    from config.logger import trading_logger as logger
    from config.settings import settings

    # Determinar modo dry_run
    # Si no se pasa --live explícitamente, default es dry_run=True (seguro)
    dry_run = not args.live or args.dry_run

    logger.info("Iniciando Tincho Bot...")
    logger.info(
        "Modo: %s | Testnet: %s | API: %s",
        "DRY-RUN" if dry_run else "LIVE",
        settings.binance_testnet,
        "DESACTIVADA" if args.no_api else f"http://localhost:{settings.api_port}",
    )

    if not dry_run and not settings.binance_testnet:
        logger.warning("=" * 60)
        logger.warning("  MODO LIVE EN MAINNET — SE USARÁ DINERO REAL")
        logger.warning("  Asegúrate de haber probado en testnet primero.")
        logger.warning("=" * 60)

    if args.interval:
        from agent.parameters_manager import parameters_manager
        parameters_manager.params.analysis_interval_seconds = args.interval
        logger.info("Intervalo de análisis forzado a %ds (via --interval)", args.interval)

    if args.no_api:
        # Iniciar solo el agente sin API
        from agent.trading_agent import TradingAgent
        agent = TradingAgent(dry_run=dry_run, interval_override=args.interval, force_ai=args.force_ai)
        agent.start()
    else:
        from app.agent_runner import AgentRunner
        runner = AgentRunner(dry_run=dry_run, interval_override=args.interval, force_ai=args.force_ai)
        runner.run()


if __name__ == "__main__":
    main()
