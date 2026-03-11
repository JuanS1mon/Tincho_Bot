"""
App - Main
============
Flujo principal del bot de trading (13 pasos).
Orquesta todos los módulos del sistema en cada ciclo de ejecución.

Flujo:
  ① Obtener balance de Binance
  ② Actualizar portfolio dinámico
  ③ Descargar datos de mercado (REST)
  ④ Calcular indicadores técnicos
  ⑤ Analizar order book (REST)
  ⑥ Detectar ballenas (REST)
  ⑦ Verificar manipulación
  ⑧ Analizar mercado (generar snapshots)
  ⑨ Ejecutar simulación obligatoria
  ⑩ Generar prompt IA (con datos avanzados + pesos aprendidos)
  ⑪ Recibir y validar decisión de la IA
  ⑫ Validar riesgo
  ⑬ Ejecutar trade + guardar logs
"""

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Agregar raíz del proyecto al path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings
from config.logger import setup_logging, get_logger
from domain.entities.portfolio import Portfolio
from domain.entities.market_data import MarketData, MarketSnapshot
from domain.entities.trade_signal import TradeSignal
from domain.services.market_analyzer import MarketAnalyzer
from domain.services.risk_manager import RiskManager
from domain.services.capital_allocator import CapitalAllocator
from infrastructure.binance.binance_client import BinanceClientWrapper
from infrastructure.binance.order_executor import OrderExecutor
from infrastructure.ai.ai_client import AIClient
from infrastructure.ai.ai_prompt_builder import AIPromptBuilder
from infrastructure.storage.database import Database
from infrastructure.storage.repositories import (
    TradeRepository,
    MarketSnapshotRepository,
    AIDecisionRepository,
    SimulationResultRepository,
    PortfolioHistoryRepository,
    WhaleAlertRepository,
    OrderBookSnapshotRepository,
    IndicatorWeightRepository,
)
from simulation.strategy_simulator import StrategySimulator
from advanced.whale_detector import WhaleDetector
from advanced.orderbook_analyzer import OrderBookAnalyzer
from advanced.manipulation_detector import ManipulationDetector
from advanced.learning_engine import LearningEngine

logger = get_logger(__name__)


class TradingBot:
    """
    Bot de trading principal.
    Orquesta el flujo completo de 13 pasos en cada ciclo.
    """

    def __init__(self):
        """Inicializa todos los componentes del bot."""
        setup_logging()
        self._print_banner()

        # --- Infraestructura ---
        logger.info("Inicializando componentes...")
        self.db = Database()
        self.binance = BinanceClientWrapper()
        self.executor = OrderExecutor(self.binance)
        self.ai_client = AIClient()
        self.prompt_builder = AIPromptBuilder()

        # --- Repositorios ---
        self.trade_repo = TradeRepository(self.db)
        self.snapshot_repo = MarketSnapshotRepository(self.db)
        self.ai_decision_repo = AIDecisionRepository(self.db)
        self.simulation_repo = SimulationResultRepository(self.db)
        self.portfolio_repo = PortfolioHistoryRepository(self.db)
        self.whale_repo = WhaleAlertRepository(self.db)
        self.orderbook_repo = OrderBookSnapshotRepository(self.db)
        self.weight_repo = IndicatorWeightRepository(self.db)

        # --- Servicios de dominio ---
        self.market_analyzer = MarketAnalyzer()
        self.risk_manager = RiskManager()
        self.capital_allocator = CapitalAllocator()

        # --- Simulación ---
        self.strategy_simulator = StrategySimulator()

        # --- Módulos avanzados ---
        self.whale_detector = WhaleDetector()
        self.orderbook_analyzer = OrderBookAnalyzer()
        self.manipulation_detector = ManipulationDetector()
        self.learning_engine = LearningEngine(self.weight_repo)

        # --- Estado ---
        self.portfolio = Portfolio()
        self.market_data: Dict[str, MarketData] = {}
        self.cycle_count = 0
        self._last_daily_reset = None

        logger.info("✅ Bot inicializado correctamente")

    def _print_banner(self) -> None:
        """Imprime el banner de inicio con el modo activo."""
        mode = "🟡 PAPER TRADING" if settings.is_paper_mode else "🔴 LIVE TRADING"
        banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                  🤖 CRYPTO TRADING BOT                       ║
║                                                              ║
║  Modo:     {mode:<47}║
║  Capital:  {settings.INITIAL_CAPITAL:<47}║
║  Símbolos: {', '.join(settings.SYMBOLS):<47}║
║  IA:       {settings.AI_PROVIDER}/{settings.AI_MODEL:<40}║
║  Intervalo: Cada {settings.EXECUTION_INTERVAL_MINUTES} minutos{' ' * 33}║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝"""
        print(banner)
        logger.info(f"Bot iniciado en modo {mode}")

    def run_cycle(self) -> None:
        """
        Ejecuta un ciclo completo del bot (13 pasos).
        Este método se invoca cada EXECUTION_INTERVAL_MINUTES.
        """
        self.cycle_count += 1
        cycle_start = datetime.utcnow()
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 CICLO #{self.cycle_count} - {cycle_start.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"{'='*60}")

        try:
            # --- Resetear tracking diario si es un nuevo día ---
            self._check_daily_reset()

            # ① Obtener balance de Binance
            logger.info("① Obteniendo balance...")
            balance_usdt = self._get_balance()

            # ② Actualizar portfolio dinámico
            logger.info("② Actualizando portfolio...")
            prices = self._get_current_prices()
            self.portfolio.update_balance(balance_usdt, prices)

            # ③ Descargar datos de mercado (REST)
            logger.info("③ Descargando datos de mercado...")
            self._download_market_data()

            # ④ Calcular indicadores + ⑧ Analizar mercado
            logger.info("④⑧ Calculando indicadores y analizando mercado...")
            snapshots = self._analyze_markets()

            if not snapshots:
                logger.warning("⚠️ Sin datos suficientes para análisis. Ciclo omitido.")
                return

            # ⑤ Analizar order book (REST)
            logger.info("⑤ Analizando order book...")
            orderbook_analysis = self._analyze_order_books()

            # ⑥ Detectar ballenas (REST)
            logger.info("⑥ Detectando actividad de ballenas...")
            whale_alerts = self._detect_whales()

            # ⑦ Verificar manipulación
            logger.info("⑦ Verificando manipulación de mercado...")
            manipulation_flags = self._detect_manipulation()

            # ⑨ Ejecutar simulación obligatoria
            logger.info("⑨ Ejecutando simulación obligatoria...")
            simulation_result = self._run_simulation()

            if not simulation_result.approved:
                logger.warning(f"🚫 Simulación no aprobada: {simulation_result.reason}")
                self._save_cycle_data(snapshots, None, simulation_result.to_dict(), prices)
                return

            # ⑩ Generar prompt IA (con datos avanzados + pesos aprendidos)
            logger.info("⑩ Generando prompt para IA...")
            capital = self.portfolio.capital_actual(prices)
            indicator_weights = self.learning_engine.get_weights()

            system_prompt = self.prompt_builder.build_system_prompt()
            user_prompt = self.prompt_builder.build_user_prompt(
                capital=capital,
                max_capital_usage=settings.MAX_CAPITAL_USAGE,
                snapshots=snapshots,
                orderbook_analysis=orderbook_analysis,
                whale_alerts=[a for alerts in whale_alerts.values() for a in alerts.get("alerts", [])],
                manipulation_flags={s: m["manipulation_detected"] for s, m in manipulation_flags.items()},
                indicator_weights=indicator_weights,
                simulation_results=simulation_result.to_dict(),
            )

            # ⑪ Recibir y validar decisión de la IA
            logger.info("⑪ Consultando IA para decisión de trading...")
            ai_response = self.ai_client.get_trading_decision(system_prompt, user_prompt)

            if not ai_response:
                logger.warning("⚠️ Sin respuesta de la IA. Ciclo omitido.")
                return

            signal = TradeSignal.from_ai_response(ai_response)

            # ⑫ Validar riesgo
            logger.info("⑫ Validando condiciones de riesgo...")
            any_manipulation = any(
                m["manipulation_detected"] for m in manipulation_flags.values()
            )
            risk_validation = self.risk_manager.validate(
                signal=signal,
                portfolio=self.portfolio,
                prices=prices,
                manipulation_detected=any_manipulation,
            )

            if not risk_validation.approved:
                logger.info(f"⛔ Riesgo no aprobado: {risk_validation.reason}")
                self._save_cycle_data(snapshots, signal, simulation_result.to_dict(), prices)
                return

            # ⑬ Ejecutar trade + guardar logs
            logger.info("⑬ Ejecutando trades...")
            orders = self.capital_allocator.allocate(
                signal=signal,
                portfolio=self.portfolio,
                prices=prices,
                risk_validation=risk_validation,
            )

            if orders:
                results = self.executor.execute_orders(orders)
                self._save_trades(results, prices)

                # Actualizar posiciones del portfolio
                for order, result in zip(orders, results):
                    if result.get("status") == "FILLED":
                        self.portfolio.add_position(
                            symbol=order.symbol,
                            quantity=order.quantity,
                            price=order.price,
                        )
            else:
                logger.info("Sin órdenes para ejecutar en este ciclo")

            # --- Guardar datos del ciclo ---
            self._save_cycle_data(snapshots, signal, simulation_result.to_dict(), prices)

            # --- Equity snapshot ---
            self.portfolio.save_equity_snapshot(prices)

            cycle_duration = (datetime.utcnow() - cycle_start).total_seconds()
            logger.info(f"✅ Ciclo #{self.cycle_count} completado en {cycle_duration:.1f}s")

        except Exception as e:
            logger.error(f"❌ Error en ciclo #{self.cycle_count}: {e}")
            logger.error(traceback.format_exc())

    # ================================================================
    # Métodos auxiliares del flujo
    # ================================================================

    def _get_balance(self) -> float:
        """Obtiene el balance USDT de Binance o del paper trading."""
        if settings.is_paper_mode:
            paper_balance = self.executor.get_paper_balance()
            return paper_balance.get("USDT", settings.INITIAL_CAPITAL)
        return self.binance.get_balance("USDT")

    def _get_current_prices(self) -> Dict[str, float]:
        """Obtiene precios actuales de todos los símbolos."""
        return self.binance.get_prices(settings.SYMBOLS)

    def _download_market_data(self) -> None:
        """Descarga klines de Binance para todos los símbolos e intervalos."""
        for symbol in settings.SYMBOLS:
            if symbol not in self.market_data:
                self.market_data[symbol] = MarketData(symbol=symbol)

            for interval in settings.INTERVALS:
                df = self.binance.get_klines(
                    symbol=symbol,
                    interval=interval,
                    days=settings.ANALYSIS_DAYS,
                )
                if not df.empty:
                    self.market_data[symbol].set_klines(interval, df)

            # Actualizar precio actual
            price = self.binance.get_ticker_price(symbol)
            self.market_data[symbol].current_price = price

    def _analyze_markets(self) -> Dict[str, MarketSnapshot]:
        """Analiza todos los mercados y genera snapshots."""
        snapshots = {}
        for symbol, data in self.market_data.items():
            snapshot = self.market_analyzer.analyze(data, interval=settings.INTERVALS[0])
            if snapshot:
                snapshots[symbol] = snapshot
        return snapshots

    def _analyze_order_books(self) -> Dict[str, dict]:
        """Analiza el order book de cada símbolo."""
        analysis = {}
        for symbol in settings.SYMBOLS:
            ob = self.binance.get_order_book(symbol)
            analysis[symbol] = self.orderbook_analyzer.analyze(symbol, ob)

            # Guardar snapshot en DB
            self.orderbook_repo.save(analysis[symbol])
        return analysis

    def _detect_whales(self) -> Dict[str, dict]:
        """Detecta actividad de ballenas en cada símbolo."""
        whale_data = {}
        for symbol in settings.SYMBOLS:
            ob = self.binance.get_order_book(symbol, limit=500)
            trades = self.binance.get_recent_trades(symbol, limit=500)
            result = self.whale_detector.analyze(symbol, ob, trades)
            whale_data[symbol] = result

            # Guardar alertas en DB
            for alert in result.get("alerts", []):
                self.whale_repo.save(alert)
        return whale_data

    def _detect_manipulation(self) -> Dict[str, dict]:
        """Verifica manipulación en cada símbolo."""
        manipulation = {}
        for symbol in settings.SYMBOLS:
            data = self.market_data.get(symbol)
            if not data:
                continue

            df = data.get_klines(settings.INTERVALS[0])
            ob = self.binance.get_order_book(symbol)
            trades = self.binance.get_recent_trades(symbol)

            result = self.manipulation_detector.detect(symbol, df, ob, trades)
            manipulation[symbol] = result
        return manipulation

    def _run_simulation(self):
        """Ejecuta backtesting + Monte Carlo."""
        klines = {}
        for symbol in settings.SYMBOLS:
            data = self.market_data.get(symbol)
            if data:
                df = data.get_klines(settings.INTERVALS[0])
                if df is not None:
                    klines[symbol] = df

        return self.strategy_simulator.run_full_simulation(klines)

    def _save_trades(self, results: List[dict], prices: Dict[str, float]) -> None:
        """Guarda los trades ejecutados en la base de datos."""
        for result in results:
            result["mode"] = settings.TRADING_MODE
            self.trade_repo.save(result)

    def _save_cycle_data(
        self,
        snapshots: Dict[str, MarketSnapshot],
        signal: Optional[TradeSignal],
        simulation_data: dict,
        prices: Dict[str, float],
    ) -> None:
        """Guarda todos los datos del ciclo en la base de datos."""
        # Market snapshots
        for symbol, snapshot in snapshots.items():
            self.snapshot_repo.save(snapshot.to_dict())

        # AI decision
        if signal:
            self.ai_decision_repo.save(signal.to_dict())

        # Simulation results
        self.simulation_repo.save(simulation_data)

        # Portfolio history
        self.portfolio_repo.save({
            "balance_usdt": self.portfolio.balance_usdt,
            "positions_value": self.portfolio.positions_value_usdt(prices),
            "total_capital": self.portfolio.capital_actual(prices),
            "daily_pnl": self.portfolio.daily_pnl,
        })

    def _check_daily_reset(self) -> None:
        """Resetea el tracking diario si cambió el día."""
        today = datetime.utcnow().date()
        if self._last_daily_reset != today:
            prices = self._get_current_prices()
            self.portfolio.reset_daily_tracking(prices)
            self._last_daily_reset = today
            logger.info(f"📅 Nuevo día: {today}")

    def shutdown(self) -> None:
        """Limpieza al cerrar el bot."""
        logger.info("Cerrando bot...")
        self.db.close()
        logger.info("👋 Bot cerrado correctamente")


def main():
    """Punto de entrada para ejecución directa de un ciclo."""
    bot = TradingBot()
    try:
        bot.run_cycle()
    finally:
        bot.shutdown()


if __name__ == "__main__":
    main()
