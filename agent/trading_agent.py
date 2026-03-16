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
from tools.portfolio_tool import portfolio_tool, Position
from exchange.order_manager import order_manager
from storage.trade_repository import trade_repository
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class TradingAgent:
    """Agente autónomo de trading de criptomonedas."""

    def __init__(self, dry_run: bool = True, interval_override: int | None = None, force_ai: bool = False, tryhard: bool = False) -> None:
        self.dry_run = dry_run
        self.force_ai = force_ai  # activa consulta IA en ciclo 1 y cuando hay cambios de mercado
        self.state = AgentState()
        self._running = False
        self._stop_event = threading.Event()
        # Tracking de tendencias/señales previas para detectar cambios
        self._prev_trends: Dict[str, str] = {}   # symbol → "BULLISH"|"BEARISH"|"NEUTRAL"
        self._prev_signals: Dict[str, str] = {}  # symbol → "LONG"|"SHORT"|"NO_SIGNAL"

        # Restaurar parámetros dinámicos desde MongoDB (ajustes previos de la IA)
        parameters_manager.load_from_db()

        if tryhard:
            parameters_manager.params.tryhard_mode = True
            logger.info("🔥 [TRYHARD] Modo activado: se relajan filtros de volumen y proximidad SMA20")

        # Aplicar override de intervalo si se pasó por CLI (tiene prioridad sobre DB)
        if interval_override is not None:
            parameters_manager.params.analysis_interval_seconds = interval_override
            logger.info("Intervalo forzado a %ds (simulación via --interval)", interval_override)

        # Sincronizar capital con saldo real de Binance Futures
        portfolio_tool.sync_from_exchange()

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
        # ── Paso 0: Sincronizar balance, reconstruir posiciones y cierres ───────
        portfolio_tool.sync_from_exchange()
        self._recover_open_positions_from_exchange()
        self._sync_closed_positions()

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
        # ── Paso 4.5: Tincho1 analiza condiciones globales y ajusta parámetros ──
        # Solo ejecutar si hay cambios relevantes en el mercado (ejemplo: cambio de tendencia, volumen, señales nuevas)
        cambios_relevantes = any(
            s.signal != "NO_SIGNAL" or abs(s.confidence) > 0.7 for s in signals.values()
        )
        if all_market_data and cambios_relevantes:
            try:
                decision_engine.market_overview_adjust(all_market_data, self.state)
            except Exception as exc:
                error_logger.error("Error en market_overview_adjust: %s", exc)

        for symbol, signal in signals.items():
            if signal.signal == "NO_SIGNAL":
                # --force-ai: ciclo 1 O cuando cambia la tendencia/señal
                if self.force_ai:
                    trend_now = all_market_data.get(symbol, {}).get("trend", "")
                    trend_changed = trend_now != self._prev_trends.get(symbol, "")
                    signal_changed = signal.signal != self._prev_signals.get(symbol, "")
                    is_first_cycle = self.state.cycle == 1

                    if is_first_cycle or trend_changed or signal_changed:
                        motivo = "ciclo 1" if is_first_cycle else ("cambio de tendencia" if trend_changed else "cambio de señal")
                        logger.info(
                            "[%s] Sin señal | %s | [--force-ai] consultando IA (%s)...",
                            symbol, signal.reason, motivo,
                        )
                        try:
                            snap: MarketSnapshot = market_data_tool.get(symbol)
                            futures_snap = futures_data_tool.get(
                                symbol,
                                current_price=snap.ticker["price"],
                                prev_price=float(snap.df["close"].iloc[-2]) if len(snap.df) > 1 else snap.ticker["price"],
                            )
                            decision_engine.consult_ai_only(
                                symbol=symbol,
                                df=snap.df,
                                indicators=snap.indicators,
                                volume_analysis=volume_analyzer.analyze(snap.df),
                                oi_analysis=futures_snap.oi_analysis,
                                funding_rate=futures_snap.funding_rate,
                                all_market_data=all_market_data,
                                state=self.state,
                            )
                        except Exception as exc:
                            error_logger.error("Error en consulta IA forzada para %s: %s", symbol, exc)
                    else:
                        logger.info("[%s] Sin señal | %s", symbol, signal.reason)
                else:
                    logger.info("[%s] Sin señal | %s", symbol, signal.reason)

                # Actualizar estado previo
                self._prev_trends[symbol] = all_market_data.get(symbol, {}).get("trend", "")
                self._prev_signals[symbol] = signal.signal
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

        # ── Paso 9: Monitorear posiciones BULLISH (meme coins fuera del loop) ──
        manual_positions = {
            sym: pos for sym, pos in portfolio_tool.positions.items()
            if sym not in settings.symbols
        }
        for sym, pos in manual_positions.items():
            current_price = pos.entry_price
            # Intentar precio actual del exchange
            try:
                from tools.order_manager import order_manager
                ticker = order_manager._client.safe_call(
                    order_manager._client.client.futures_symbol_ticker,
                    symbol=sym,
                )
                current_price = float(ticker["price"])
                # Actualizar snapshot para que el frontend lo vea
                self.state.update_market(MarketSnapshotState(
                    symbol=sym,
                    price=current_price,
                    trend="BULLISH" if current_price >= pos.entry_price else "BEARISH",
                    rsi=50.0,
                    sma20=current_price,
                    sma50=current_price,
                    volume_trend="NEUTRAL",
                    oi_trend="NEUTRAL",
                    oi_signal="NEUTRAL",
                    funding_rate=0.0,
                    orderbook_imbalance=0.0,
                    liquidation_signal="NEUTRAL",
                ))
            except Exception:
                pass
            if pos.direction == "LONG":
                unrealized_pnl = (current_price - pos.entry_price) * pos.quantity
            else:
                unrealized_pnl = (pos.entry_price - current_price) * pos.quantity
            unrealized_pct = (unrealized_pnl / pos.capital_used * 100) if pos.capital_used > 0 else 0.0
            pnl_sign = "+" if unrealized_pnl >= 0 else ""
            logger.info(
                "[%s] 🐂 posición %s | entrada=%.6f | actual=%.6f | P&L=%s%.4f USDT (%s%.2f%%) | capital=%.2f USDT",
                sym, pos.direction, pos.entry_price, current_price,
                pnl_sign, unrealized_pnl, pnl_sign, unrealized_pct, pos.capital_used,
            )

    # ── Sincronización de cierres (SL/TP) ───────────────────────────────────

    def _recover_open_positions_from_exchange(self) -> None:
        """
        En modo real, reconstruye posiciones abiertas desde Binance tras un reinicio.

        Esto permite que el agente vuelva a monitorear una posición ya existente,
        detectar si se cerró por SL/TP mientras el proceso estaba caído y reflejarlo
        correctamente en el portafolio interno.
        """
        if self.dry_run:
            return

        try:
            open_positions = order_manager.get_open_positions()
        except Exception as exc:
            error_logger.error("Error recuperando posiciones abiertas desde Binance: %s", exc)
            return

        for exchange_pos in open_positions:
            try:
                symbol = str(exchange_pos.get("symbol", ""))
                if not symbol or portfolio_tool.has_open_position(symbol):
                    continue

                position_amt = float(exchange_pos.get("positionAmt", 0) or 0)
                if position_amt == 0:
                    continue

                entry_price = float(exchange_pos.get("entryPrice", 0) or 0)
                if entry_price <= 0:
                    continue

                quantity = abs(position_amt)
                direction = "LONG" if position_amt > 0 else "SHORT"

                leverage = int(float(exchange_pos.get("leverage", settings.leverage) or settings.leverage))
                notional = abs(float(exchange_pos.get("notional", 0) or 0))
                capital_used = notional / max(leverage, 1) if notional > 0 else (entry_price * quantity) / max(leverage, 1)

                stop_loss = 0.0
                take_profit = 0.0
                open_orders = order_manager.get_open_orders(symbol=symbol)
                close_side = "SELL" if direction == "LONG" else "BUY"
                for order in open_orders:
                    if order.get("side") != close_side:
                        continue
                    order_type = str(order.get("type", ""))
                    stop_price = float(order.get("stopPrice", 0) or 0)
                    if stop_price <= 0:
                        continue
                    if order_type == "STOP_MARKET":
                        stop_loss = stop_price
                    elif order_type == "TAKE_PROFIT_MARKET":
                        take_profit = stop_price

                recovered = Position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    quantity=quantity,
                    capital_used=capital_used,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    order_id=str(exchange_pos.get("symbol", "")),
                )
                portfolio_tool.open_position(recovered)
                self.state.add_recovered_position(
                    symbol=symbol,
                    direction=direction,
                    entry_price=entry_price,
                    quantity=quantity,
                )
                logger.warning(
                    "[%s] Posición recuperada tras reinicio | dir=%s | entry=%.6f | qty=%.6f | SL=%.6f | TP=%.6f",
                    symbol, direction, entry_price, quantity, stop_loss, take_profit,
                )
                self.state.add_log(
                    f"Posición recuperada tras reinicio: {direction} {symbol} @ {entry_price:.6f}"
                )
            except Exception as exc:
                error_logger.error("Error recuperando posición %s: %s", exchange_pos.get('symbol'), exc)

    def _sync_closed_positions(self) -> None:
        """
        Detecta posiciones que fueron cerradas (por SL, TP o trailing stop)
        y actualiza el portafolio interno.

        - dry_run: compara precio actual contra SL/TP registrados.
        - real:    consulta Binance y detecta posiciones que ya no existen.
        """
        if not portfolio_tool.positions:
            return

        symbols_to_check = list(portfolio_tool.positions.keys())

        for symbol in symbols_to_check:
            pos = portfolio_tool.positions.get(symbol)
            if pos is None:
                continue
            try:
                self._check_position_closed(symbol, pos)
            except Exception as exc:
                error_logger.error("[%s] Error en _sync_closed_positions: %s", symbol, exc)

    def _check_position_closed(self, symbol: str, pos) -> None:
        """Evalúa si una posición fue cerrada y registra el cierre."""
        import time as _time

        if self.dry_run:
            # ── Dry-run: simular SL/TP con precio actual ──────────────────────
            try:
                ticker = order_manager._client.safe_call(
                    order_manager._client.client.futures_symbol_ticker,
                    symbol=symbol,
                )
                current_price = float(ticker["price"])
            except Exception:
                return  # sin precio, no podemos evaluar

            hit_sl = (
                (pos.direction == "LONG"  and current_price <= pos.stop_loss) or
                (pos.direction == "SHORT" and current_price >= pos.stop_loss)
            )
            has_tp = pos.take_profit > 0
            hit_tp = has_tp and (
                (pos.direction == "LONG"  and current_price >= pos.take_profit) or
                (pos.direction == "SHORT" and current_price <= pos.take_profit)
            )

            if not hit_sl and not hit_tp:
                return

            exit_price = pos.stop_loss if hit_sl else pos.take_profit
            strategy = "SL_HIT" if hit_sl else "TP_HIT"
            outcome = "❌ SL" if hit_sl else "✅ TP"

        else:
            # ── Real: consultar si Binance todavía tiene la posición abierta ──
            open_positions = order_manager.get_open_positions(symbol=symbol)
            still_open = any(
                float(p.get("positionAmt", 0)) != 0 for p in open_positions
            )
            if still_open:
                return  # Binance sigue con la posición, nada que hacer

            # Obtener precio de salida del historial reciente de trades
            exit_price = None
            try:
                trades = order_manager._client.safe_call(
                    order_manager._client.client.futures_account_trades,
                    symbol=symbol,
                    limit=10,
                )
                # Filtrar solo trades de cierre (reduceOnly)
                close_trades = [t for t in trades if t.get("buyer") is not None]
                if close_trades:
                    # El más reciente
                    last = max(close_trades, key=lambda t: t.get("time", 0))
                    exit_price = float(last["price"])
            except Exception:
                pass

            if exit_price is None:
                # Fallback: precio actual del mercado
                try:
                    ticker = order_manager._client.safe_call(
                        order_manager._client.client.futures_symbol_ticker,
                        symbol=symbol,
                    )
                    exit_price = float(ticker["price"])
                except Exception:
                    return

            # Determinar si fue SL o TP según el precio de salida
            if pos.direction == "LONG":
                hit_sl = exit_price <= pos.stop_loss * 1.005  # pequeño margen de slippage
            else:
                hit_sl = exit_price >= pos.stop_loss * 0.995
            if pos.take_profit <= 0:
                strategy = "MANUAL_EXIT"
                outcome = "ℹ️ CIERRE"
            else:
                strategy = "SL_HIT" if hit_sl else "TP_HIT"
                outcome = "❌ SL" if hit_sl else "✅ TP"

        # ── Registrar cierre en portafolio ────────────────────────────────────
        record = portfolio_tool.close_position(symbol, exit_price, strategy=strategy)
        if record is None:
            return

        mode = "[DRY-RUN]" if self.dry_run else "[REAL]"
        logger.info(
            "%s %s [%s] %s | entrada=%.6f | salida=%.6f | PnL=%+.4f USDT (%+.2f%%) | capital=%.2f USDT",
            mode, outcome, strategy, symbol,
            record.entry_price, record.exit_price,
            record.pnl, record.pnl_pct,
            portfolio_tool.capital,
        )
        self.state.add_log(
            f"{mode} {outcome} {symbol} | PnL={record.pnl:+.4f} USDT | capital={portfolio_tool.capital:.2f} USDT"
        )

        # ── Persistir en MongoDB ──────────────────────────────────────────────
        trade_repository.save_trade({
            "symbol": record.symbol,
            "direction": record.direction,
            "entry_price": record.entry_price,
            "exit_price": record.exit_price,
            "quantity": record.quantity,
            "pnl": record.pnl,
            "pnl_pct": record.pnl_pct,
            "strategy": record.strategy,
            "duration_seconds": record.duration_seconds,
            "dry_run": self.dry_run,
        })

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

        # 6. Actualizar historial RSI y calcular momentum antes de detectar señal
        self.state.push_rsi(symbol, ind.rsi)
        rsi_momentum = self.state.get_rsi_momentum(symbol)

        # 6. Detectar señal de trading
        signal = signal_detector.detect(df, ind, vol_analysis, futures_snap.oi_analysis, rsi_momentum=rsi_momentum)

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
            "rsi_momentum": rsi_momentum,
            "rsi_history": self.state.rsi_history.get(symbol, []),
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

        prox_pct = abs(ind.price - ind.sma20) / ind.sma20 * 100 if ind.sma20 > 0 else 0
        logger.info(
            "[%s] precio=%.4f | trend=%s | RSI=%.1f | SMA20dist=%.2f%% | vol=%.2fx | OI=%s | señal=%s (%s)",
            symbol, ind.price, trend, ind.rsi, prox_pct,
            vol_analysis.volume_ratio,
            futures_snap.oi_analysis.trend, signal.signal, signal.strategy,
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
