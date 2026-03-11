"""
agent/trading_agent.py
=======================
Loop principal del agente autónomo de trading.

Ciclo de ejecución (cada ANALYSIS_INTERVAL_SECONDS):
  1. Obtener datos de mercado
  2. Calcular indicadores
  3. Analizar datos avanzados de futuros
  4. Detectar señales
  5. Simular → consultar IA → validar riesgo → ejecutar
  6. Actualizar portafolio
  7. Guardar estado y logs
"""
from __future__ import annotations

import time
import threading
from typing import Dict, Optional

from tools.market_data_tool import market_data_tool, MarketSnapshot
from tools.futures_data_tool import futures_data_tool
from analysis.trend_detector import trend_detector
from analysis.volume_analyzer import volume_analyzer
from analysis.orderbook_analyzer import orderbook_analyzer
from analysis.signal_detector import signal_detector, TradingSignal
from agent.decision_engine import decision_engine
from agent.state_manager import AgentState, MarketSnapshot as MarketSnapshotState, SignalState
from agent.parameters_manager import parameters_manager
from storage.state_repository import state_repository
from tools.portfolio_tool import portfolio_tool
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class TradingAgent:
    """Agente autónomo de trading de criptomonedas."""

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self.state = AgentState()
        self._running = False
        self._stop_event = threading.Event()

        # Restaurar parámetros dinámicos desde MongoDB (ajustes previos de la IA)
        parameters_manager.load_from_db()

        # Configurar dry_run en el motor de decisión
        decision_engine.dry_run = dry_run

        logger.info(
            "TradingAgent inicializado | símbolos=%s | dry_run=%s | testnet=%s",
            settings.symbols, dry_run, settings.binance_testnet,
        )
        logger.info("Parámetros dinámicos actuales | %s", parameters_manager.summary())

    # ── Control del loop ─────────────────────────────────────────────────────

    def start(self) -> None:
        """Inicia el loop del agente en el hilo actual (bloqueante)."""
        self._running = True
        self._stop_event.clear()
        self.state.status = "ANALYZING"
        interval = parameters_manager.params.analysis_interval_seconds
        logger.info("Agente iniciado. Intervalo de análisis: %ds", interval)
        self._run_loop()

    def stop(self) -> None:
        """Detiene el loop de forma graceful."""
        logger.info("Deteniendo agente...")
        self._running = False
        self._stop_event.set()
        self.state.status = "STOPPED"

    # ── Loop principal ────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        """Loop principal while True con manejo de errores y sleep inteligente."""
        while self._running and not self._stop_event.is_set():
            cycle_start = time.time()
            self.state.cycle += 1

            logger.info("=" * 60)
            logger.info("CICLO #%d | %s", self.state.cycle, time.strftime("%Y-%m-%d %H:%M:%S"))
            logger.info("=" * 60)
            self.state.add_log(f"Inicio ciclo #{self.state.cycle}")

            try:
                self.state.status = "ANALYZING"
                self._run_cycle()
                self.state.status = "IDLE"
                self.state.last_error = ""

            except KeyboardInterrupt:
                logger.info("Interrupción manual recibida.")
                break
            except Exception as exc:
                self.state.status = "ERROR"
                self.state.last_error = str(exc)
                error_logger.error("Error en ciclo #%d: %s", self.state.cycle, exc, exc_info=True)

            # Guardar estado después de cada ciclo
            self.state.last_cycle_time = time.time()
            self._persist_state()

            # Calcular tiempo de espera restante — usa el intervalo dinámico
            elapsed = time.time() - cycle_start
            wait = max(0, parameters_manager.params.analysis_interval_seconds - elapsed)
            logger.info("Ciclo completado en %.1fs. Próximo análisis en %.1fs.", elapsed, wait)

            self._stop_event.wait(timeout=wait)

    # ── Ciclo de análisis ─────────────────────────────────────────────────────

    def _run_cycle(self) -> None:
        """Ejecuta un ciclo completo de análisis para todos los símbolos."""
        all_market_data: Dict[str, dict] = {}
        signals: Dict[str, TradingSignal] = {}

        # ── Paso 1-4: Recopilar datos y detectar señales ──────────────────────
        for symbol in settings.symbols:
            try:
                market_data = self._analyze_symbol(symbol, all_market_data)
                if market_data:
                    signal = market_data["signal"]
                    signals[symbol] = signal

                    # Actualizar estado del agente
                    self.state.update_signal(SignalState(
                        symbol=symbol,
                        signal=signal.signal,
                        strategy=signal.strategy,
                        confidence=signal.confidence,
                        reason=signal.reason,
                    ))

            except Exception as exc:
                error_logger.error("Error analizando %s: %s", symbol, exc)

        # ── Paso 5-7: Evaluar señales y ejecutar trades ────────────────────────
        for symbol, signal in signals.items():
            if signal.signal == "NO_SIGNAL":
                logger.info("[%s] Sin señal detectada.", symbol)
                continue

            logger.info(
                "[%s] Señal: %s (%s) | conf=%.0f%% | %s",
                symbol, signal.signal, signal.strategy,
                signal.confidence * 100, signal.reason,
            )

            try:
                snap: MarketSnapshot = market_data_tool.get(symbol)
                futures_snap = futures_data_tool.get(
                    symbol,
                    current_price=snap.ticker["price"],
                    prev_price=float(snap.df["close"].iloc[-2]) if len(snap.df) > 1 else snap.ticker["price"],
                )

                executed, reason = decision_engine.evaluate(
                    signal=signal,
                    symbol=symbol,
                    df=snap.df,
                    indicators=snap.indicators,
                    volume_analysis=volume_analyzer.analyze(snap.df),
                    oi_analysis=futures_snap.oi_analysis,
                    funding_rate=futures_snap.funding_rate,
                    all_market_data=all_market_data,
                    state=self.state,
                )
                logger.info("[%s] Resultado: %s — %s", symbol, "EJECUTADO" if executed else "OMITIDO", reason)

            except Exception as exc:
                error_logger.error("Error evaluando señal para %s: %s", symbol, exc)

        # ── Paso 8: Estado del portafolio ─────────────────────────────────────
        port = portfolio_tool.get_state_dict()
        logger.info(
            "Portafolio: capital=%.2f USDT | pnl=%.4f | posiciones=%d | win_rate=%.1f%%",
            port["capital"], port["total_pnl"],
            port["open_positions"], port["win_rate"] * 100,
        )

    # ── Análisis de un símbolo ────────────────────────────────────────────────

    def _analyze_symbol(self, symbol: str, all_market_data: dict) -> Optional[dict]:
        """
        Recopila y analiza todos los datos de un símbolo.
        Actualiza all_market_data con los datos para el prompt de IA.
        Retorna dict con snapshot, indicadores, análisis y señal.
        """
        # 1. Datos básicos de mercado
        snap: MarketSnapshot = market_data_tool.get(symbol, force_refresh=True)
        if snap.indicators is None:
            logger.warning("[%s] Sin suficientes datos para calcular indicadores.", symbol)
            return None

        ind = snap.indicators
        df = snap.df

        # 2. Análisis de tendencia
        trend_info = trend_detector.describe(ind)
        trend = trend_info["trend"]

        # 3. Análisis de volumen
        vol_analysis = volume_analyzer.analyze(df)

        # 4. Order book
        ob_analysis = orderbook_analyzer.analyze(snap.orderbook)

        # 5. Datos de futuros (OI, funding, liquidaciones)
        prev_price = float(df["close"].iloc[-2]) if len(df) > 1 else ind.price
        futures_snap = futures_data_tool.get(
            symbol,
            current_price=ind.price,
            prev_price=prev_price,
        )

        # 6. Detectar señal de trading
        signal = signal_detector.detect(df, ind, vol_analysis, futures_snap.oi_analysis)

        # 7. Actualizar estado del agente
        self.state.update_market(MarketSnapshotState(
            symbol=symbol,
            price=ind.price,
            trend=trend,
            rsi=ind.rsi,
            sma20=ind.sma20,
            sma50=ind.sma50,
            volume_trend=vol_analysis.trend,
            oi_trend=futures_snap.oi_analysis.trend,
            oi_signal=futures_snap.oi_analysis.signal,
            funding_rate=futures_snap.funding_rate,
            orderbook_imbalance=ob_analysis.imbalance,
            liquidation_signal=futures_snap.liquidation_analysis.signal,
        ))

        # 8. Agregar al dict de datos para el prompt IA
        all_market_data[symbol] = {
            "trend": trend,
            "price": ind.price,
            "rsi": ind.rsi,
            "sma20": ind.sma20,
            "sma50": ind.sma50,
            "volume_trend": vol_analysis.trend,
            "oi_trend": futures_snap.oi_analysis.trend,
            "oi_signal": futures_snap.oi_analysis.signal,
            "funding_rate": futures_snap.funding_rate,
        }

        # 9. Persistir snapshot de mercado
        state_repository.save_market_snapshot({
            "symbol": symbol,
            "price": ind.price,
            "trend": trend,
            "rsi": ind.rsi,
            "sma20": ind.sma20,
            "sma50": ind.sma50,
            "funding_rate": futures_snap.funding_rate,
            "oi_trend": futures_snap.oi_analysis.trend,
            "signal": signal.signal,
        })

        logger.info(
            "[%s] precio=%.4f | trend=%s | RSI=%.1f | señal=%s (%s)",
            symbol, ind.price, trend, ind.rsi, signal.signal, signal.strategy,
        )

        return {"snap": snap, "indicators": ind, "signal": signal}

    # ── Persistencia de estado ────────────────────────────────────────────────

    def _persist_state(self) -> None:
        """Guarda el estado del agente y portafolio en MongoDB."""
        try:
            state_repository.save_state({
                "agent_state": self.state.to_dict(),
                "portfolio": portfolio_tool.get_state_dict(),
            })
        except Exception as exc:
            error_logger.error("Error persistiendo estado: %s", exc)

    # ── Estado público (para API) ─────────────────────────────────────────────

    def get_status(self) -> dict:
        """Retorna estado completo del agente para la API HTTP."""
        return {
            **self.state.to_dict(),
            "dry_run": self.dry_run,
            "symbols": settings.symbols,
            "analysis_interval_seconds": settings.analysis_interval_seconds,
        }
