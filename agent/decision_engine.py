"""
agent/decision_engine.py
=========================
Orquesta el pipeline de decisión para cada símbolo:

  Señal detectada
    → Simular trade
    → Consultar IA
    → Validar riesgo
    → Decisión final (ejecutar / no ejecutar)

Centraliza toda la lógica de decisión fuera del loop principal.
"""
from __future__ import annotations

from typing import Optional, Tuple

import pandas as pd

from tools.indicator_tool import Indicators
from tools.simulation_tool import simulation_tool, SimulationResult
from tools.risk_tool import risk_tool, RiskParams
from tools.portfolio_tool import portfolio_tool
from tools.execution_tool import execution_tool
from analysis.signal_detector import TradingSignal
from analysis.volume_analyzer import VolumeAnalysis
from analysis.open_interest_analyzer import OIAnalysis
from ai.llm_client import llm_client, AIDecision
from ai.decision_prompt import build_decision_prompt
from ai.tool_definitions import TINCHO1_TOOLS
from agent.state_manager import AgentState, SimulationState, AIDecisionState
from agent.parameters_manager import parameters_manager
from storage.trade_repository import trade_repository
from config.agent_config import agent_config
from config.settings import settings
from config.logger import trading_logger as logger, error_logger
from exchange.order_manager import order_manager


class DecisionEngine:
    """
    Toma una señal de trading y ejecuta el pipeline completo de validación
    antes de decidir si ejecutar o no el trade.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._min_notional_usdt = 100.0

    def evaluate(
        self,
        signal: TradingSignal,
        symbol: str,
        df: pd.DataFrame,
        indicators: Indicators,
        volume_analysis: VolumeAnalysis,
        oi_analysis: OIAnalysis,
        funding_rate: float,
        all_market_data: dict,
        state: AgentState,
    ) -> Tuple[bool, str]:
        """
        Evalúa si ejecutar el trade sugerido por la señal.
        Retorna (ejecutado: bool, motivo: str).
        """
        # ── 0. Verificar que no haya posición ya abierta ─────────────────────
        if portfolio_tool.has_open_position(symbol):
            reason = f"Ya hay posición abierta en {symbol}, saltando"
            logger.info(reason)
            state.add_log(reason)
            return False, reason
        if execution_tool.is_symbol_blocked(symbol):
            reason = f"Símbolo bloqueado: {execution_tool.get_block_reason(symbol)}"
            logger.warning("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason
        # ── 0.1 Circuit breaker de sesión ───────────────────────────────────────────────
        if portfolio_tool.circuit_breaker_active:
            reason = (
                f"🚨 Circuit breaker activo: drawdown de sesión "
                f"{portfolio_tool.session_drawdown_pct:.1%} ≥ "
                f"{portfolio_tool.CIRCUIT_BREAKER_THRESHOLD:.0%}. "
                "Trading pausado hasta próxima sesión."
            )
            logger.warning("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason

        # ── 0.2 Racha de pérdidas consecutivas ─────────────────────────────────────────
        streak = portfolio_tool.consecutive_losses
        if streak >= portfolio_tool.MAX_CONSECUTIVE_LOSSES:
            reason = (
                f"⚠️ {streak} pérdidas consecutivas — enfriamiento activado: "
                "saltando ciclo para evitar overtrading."
            )
            logger.warning("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason
        direction = signal.signal  # LONG | SHORT

        # ── 1. Simulación ─────────────────────────────────────────────────────
        logger.info("[%s] Simulando trade %s...", symbol, direction)
        sim: SimulationResult = simulation_tool.simulate(df, direction, portfolio_tool.capital)
        state.last_simulation = SimulationState(
            direction=direction,
            winrate=sim.winrate,
            expected_profit_pct=sim.expected_profit_pct,
            max_drawdown_pct=sim.max_drawdown_pct,
            recommendation=sim.recommendation,
            skip_reason=sim.skip_reason,
        )
        state.add_log(f"Simulación {direction}: winrate={sim.winrate:.1%} → {sim.recommendation}")

        if sim.recommendation == "SKIP":
            reason = f"Simulación recomienda SKIP: {sim.skip_reason}"
            logger.info("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason

        # ── 2. Hard rules algorítmicas (nunca delegar a la IA) ────────────────────
        blocked, block_reason = self._check_hard_rules(
            symbol, direction, indicators, sim, funding_rate, signal.strategy
        )
        if blocked:
            logger.info("[%s] Hard rule bloqueada: %s", symbol, block_reason)
            state.add_log(f"Hard rule: {block_reason}")
            return False, f"Hard rule: {block_reason}"

        # ── 3. Consultar IA (solo para parameter_adjustments y razonamiento) ────────

        # Cargar historial de trades recientes para enriquecer el prompt
        try:
            recent_trades = trade_repository.get_recent_trades(limit=10)
        except Exception:
            recent_trades = []

        user_prompt = build_decision_prompt(
            all_market_data,
            sim,
            dynamic_params=parameters_manager.params,
            recent_trades=recent_trades,
            target_symbol=symbol,
            target_direction=direction,
        )
        if settings.tool_calling_tincho1:
            tool_result = llm_client.decide_with_tools(
                system_prompt=agent_config.system_prompt,
                user_prompt=user_prompt,
                tools=TINCHO1_TOOLS,
                temperature=0.2,
                max_tokens=300,
            )

            if tool_result is None:
                reason = "IA no respondió o tool calling inválido — operación cancelada"
                error_logger.error("[%s] %s", symbol, reason)
                state.add_log(reason)
                return False, reason

            tool_name = (tool_result.tool_name or "").strip()
            tool_args = tool_result.arguments or {}

            if tool_name == "skip_trade":
                reason = str(tool_args.get("reason", "IA decidió no operar"))[:220]
                logger.info("[%s] 🤖 Tool skip_trade: %s", symbol, reason)
                state.add_log(f"[IA tool] skip_trade | {reason}")
                return False, reason

            if tool_name == "adjust_parameters":
                adjustments = dict(tool_args)
                rationale = str(adjustments.pop("reasoning", "Ajuste por tool calling IA"))[:200]
                changed = parameters_manager.apply_adjustments(
                    adjustments,
                    reason=f"Trade cycle tool: {rationale}",
                )
                if changed:
                    reason = f"IA ajustó parámetros y omitió trade: {adjustments}"
                    state.add_log(reason)
                    logger.info("[%s] %s", symbol, reason)
                    return False, reason
                reason = "IA pidió ajustar parámetros pero no hubo cambios válidos"
                state.add_log(reason)
                logger.info("[%s] %s", symbol, reason)
                return False, reason

            if tool_name == "close_position":
                close_symbol = str(tool_args.get("symbol", "")).upper().strip()
                close_reason = str(tool_args.get("reason", "Cierre solicitado por IA"))[:200]
                _closed, close_msg = self._close_position_from_tool(close_symbol, close_reason)
                state.add_log(f"[IA tool] close_position {close_symbol}: {close_msg}")
                logger.info("[%s] 🤖 Tool close_position: %s", symbol, close_msg)
                return False, close_msg

            if tool_name != "open_position":
                reason = f"Tool no soportada para trading: {tool_name or 'N/A'}"
                error_logger.error("[%s] %s", symbol, reason)
                state.add_log(reason)
                return False, reason

            if tool_result.fallback_decision is not None:
                ai_decision = tool_result.fallback_decision
            else:
                ai_symbol = str(tool_args.get("symbol", symbol)).upper().strip()
                ai_direction = str(tool_args.get("direction", direction)).upper().strip()
                ai_capital_usage = max(0.0, min(float(tool_args.get("capital_usage", 0.0) or 0.0), 0.50))
                ai_reasoning = str(tool_args.get("reasoning", "Decisión vía tool calling"))[:200]
                ai_decision = AIDecision(
                    trade=True,
                    symbol=ai_symbol,
                    direction=ai_direction,
                    capital_usage=ai_capital_usage,
                    confidence=1.0,
                    reasoning=ai_reasoning,
                    raw_response=tool_result.raw_response,
                    parameter_adjustments=None,
                )

            if ai_decision.symbol != symbol:
                reason = f"Tool intentó abrir {ai_decision.symbol}, pero este ciclo es de {symbol}"
                logger.info("[%s] %s", symbol, reason)
                state.add_log(reason)
                return False, reason

            if ai_decision.direction != direction:
                reason = f"Tool intentó dirección {ai_decision.direction}, esperada {direction}"
                logger.info("[%s] %s", symbol, reason)
                state.add_log(reason)
                return False, reason
        else:
            ai_decision = llm_client.decide(user_prompt)
            if ai_decision is None:
                reason = "IA no respondió o respuesta inválida — operación cancelada"
                error_logger.error("[%s] %s", symbol, reason)
                state.add_log(reason)
                return False, reason

        state.last_ai_decision = AIDecisionState(
            trade=ai_decision.trade,
            symbol=ai_decision.symbol,
            direction=ai_decision.direction,
            capital_usage=ai_decision.capital_usage,
            confidence=ai_decision.confidence,
            reasoning=ai_decision.reasoning,
        )
        decision_word = "OPERAR" if ai_decision.trade else "NO OPERAR (ignorado — hard rules OK)"
        logger.info(
            "[%s] 🤖 IA → %s | conf=%.0f%% | %s",
            symbol, decision_word, ai_decision.confidence * 100, ai_decision.reasoning,
        )
        state.add_log(
            f"[IA] {decision_word} conf={ai_decision.confidence:.0%} | {ai_decision.reasoning}"
        )

        # Bloquear si la confianza de la IA es demasiado baja (< 30%)
        if ai_decision.confidence < 0.30:
            reason = (
                f"Confianza IA insuficiente: {ai_decision.confidence:.0%} (mín 30%) — no operar"
            )
            logger.info("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason
        # La IA solo aporta parameter_adjustments y razonamiento.
        if ai_decision.parameter_adjustments:
            parameters_manager.apply_adjustments(
                ai_decision.parameter_adjustments,
                reason=f"Trade cycle: {ai_decision.reasoning}",
            )
            state.add_log(f"Parámetros ajustados por IA: {ai_decision.parameter_adjustments}")

        # ── 4. Validar riesgo ────────────────────────────────────────────────────
        # Sincronizar RiskTool con los parámetros dinámicos actuales
        risk_tool.sync_params(parameters_manager.params)

        # Capital global compartido: la IA decide cuánto usar del total disponible.
        symbol_allocation = portfolio_tool.capital
        symbol_available = portfolio_tool.available_capital
        try:
            from exchange.market_fetcher import market_fetcher
            exchange_available = market_fetcher.get_usdt_available_balance()
            if exchange_available is not None:
                symbol_available = min(symbol_available, exchange_available)
                logger.info(
                    "[%s] Capital disponible ajustado por exchange: local=%.2f | exchange=%.2f | usado=%.2f",
                    symbol,
                    portfolio_tool.available_capital,
                    exchange_available,
                    symbol_available,
                )
        except Exception as exc:
            logger.warning("[%s] No se pudo ajustar capital por exchange: %s", symbol, exc)

        current_price = indicators.price
        risk_params: RiskParams = risk_tool.validate(
            direction=direction,
            entry_price=current_price,
            available_capital=symbol_available,
            total_capital=symbol_allocation,
            capital_usage=ai_decision.capital_usage,
        )

        if not risk_params.is_valid and "Notional" in risk_params.rejection_reason:
            # Si el único bloqueo es notional mínimo, podemos subir capital_usage
            # únicamente con confluencia alta para no forzar trades débiles.
            boosted_usage = self._compute_boosted_capital_usage_for_min_notional(
                total_capital=symbol_allocation,
                available_capital=symbol_available,
                ai_capital_usage=ai_decision.capital_usage,
                leverage=risk_tool.max_leverage,
            )
            if boosted_usage is not None and self._has_high_conviction(sim, ai_decision):
                logger.info(
                    "[%s] Ajuste automático de capital_usage para mínimo notional: %.1f%% → %.1f%%",
                    symbol,
                    ai_decision.capital_usage * 100,
                    boosted_usage * 100,
                )
                risk_params = risk_tool.validate(
                    direction=direction,
                    entry_price=current_price,
                    available_capital=symbol_available,
                    total_capital=symbol_allocation,
                    capital_usage=boosted_usage,
                )
            elif boosted_usage is not None:
                logger.info(
                    "[%s] Notional bajo detectado pero sin confluencia alta: "
                    "winrate=%.1f%% conf=%.0f%% profit=%.2f%% dd=%.2f%% ruin=%.1f%%",
                    symbol,
                    sim.winrate * 100,
                    ai_decision.confidence * 100,
                    sim.expected_profit_pct,
                    sim.max_drawdown_pct,
                    sim.mc_ruin_probability * 100,
                )

        state.add_log(
            f"Riesgo: valid={risk_params.is_valid} qty={risk_params.quantity:.4f} "
            f"capital={risk_params.capital_to_use:.2f} USDT"
        )

        if not risk_params.is_valid:
            reason = f"Riesgo inválido: {risk_params.rejection_reason}"
            logger.info("[%s] %s", symbol, reason)
            return False, reason

        # ── 5. Aplicar ajustes de parámetros sugeridos por la IA ──────────────────
        # (ya aplicados antes, este bloque es solo para referencia)

        # ── 6. Ejecutar trade ───────────────────────────────────────────────
        logger.info("[%s] Ejecutando trade %s (dry_run=%s)...", symbol, direction, self.dry_run)
        result = execution_tool.execute(
            symbol=symbol,
            direction=direction,
            risk_params=risk_params,
            strategy=signal.strategy,
            dry_run=self.dry_run,
        )

        if result is None:
            reason = "Error en ejecución del trade"
            error_logger.error("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason
        if result.get("status") == "blocked":
            reason = f"Trade omitido: {result.get('reason', 'símbolo bloqueado')}"
            logger.info("[%s] %s", symbol, reason)
            state.add_log(reason)
            return False, reason

        # ── 5. Persistir log completo ─────────────────────────────────────────
        self._log_execution(symbol, direction, signal, sim, ai_decision, risk_params, result)
        state.add_log(f"✓ Trade ejecutado: {direction} {symbol} @ {current_price:.4f}")
        return True, f"Trade {direction} {symbol} ejecutado exitosamente"

    def consult_ai_only(
        self,
        symbol: str,
        df: pd.DataFrame,
        indicators: Indicators,
        volume_analysis: VolumeAnalysis,
        oi_analysis: OIAnalysis,
        funding_rate: float,
        all_market_data: dict,
        state: AgentState,
    ) -> None:
        """
        Consulta la IA aunque no haya señal técnica activa (--force-ai).
        Si la IA aprueba el trade con confianza > 60%, lo ejecuta.
        """
        from tools.simulation_tool import simulation_tool
        logger.info("[%s] [--force-ai] Consultando IA sin señal activa...", symbol)

        if execution_tool.is_symbol_blocked(symbol):
            logger.warning(
                "[%s] [--force-ai] Omitido: %s",
                symbol,
                execution_tool.get_block_reason(symbol),
            )
            return

        # Determinar dirección probable por tendencia
        from analysis.trend_detector import trend_detector, Trend
        trend = trend_detector.detect(indicators)
        direction = "SHORT" if trend == Trend.BEARISH else "LONG"

        sim = simulation_tool.simulate(df, direction, portfolio_tool.capital)

        try:
            recent_trades = trade_repository.get_recent_trades(limit=10)
        except Exception:
            recent_trades = []

        user_prompt = build_decision_prompt(
            all_market_data,
            sim,
            dynamic_params=parameters_manager.params,
            recent_trades=recent_trades,
            target_symbol=symbol,
            target_direction=direction,
        )
        ai_decision = llm_client.decide(user_prompt)

        if ai_decision is None:
            logger.warning("[%s] [--force-ai] IA no respondió", symbol)
            return

        decision_word = "OPERAR" if ai_decision.trade else "NO OPERAR"
        logger.info(
            "[%s] [IA forzada] %s | dir=%s | conf=%.0f%% | %s",
            symbol, decision_word, direction, ai_decision.confidence * 100, ai_decision.reasoning,
        )
        state.add_log(
            f"[IA force] {decision_word} conf={ai_decision.confidence:.0%} | {ai_decision.reasoning}"
        )

        # Ajustar parámetros si la IA los propone
        if ai_decision.parameter_adjustments:
            parameters_manager.apply_adjustments(
                ai_decision.parameter_adjustments,
                reason=f"force-ai: {ai_decision.reasoning}",
            )

        # Si la IA aprueba y tiene confianza suficiente → ejecutar el trade
        if ai_decision.trade and ai_decision.confidence >= 0.60:
            if portfolio_tool.has_open_position(symbol):
                logger.info("[%s] [--force-ai] IA aprobó pero ya hay posición abierta", symbol)
                return

            risk_tool.sync_params(parameters_manager.params)
            final_direction = ai_decision.direction or direction
            current_price = indicators.price
            available_capital = portfolio_tool.available_capital
            try:
                from exchange.market_fetcher import market_fetcher
                exchange_available = market_fetcher.get_usdt_available_balance()
                if exchange_available is not None:
                    available_capital = min(available_capital, exchange_available)
            except Exception:
                pass
            risk_params = risk_tool.validate(
                direction=final_direction,
                entry_price=current_price,
                available_capital=available_capital,
                total_capital=portfolio_tool.capital,
                capital_usage=ai_decision.capital_usage,
            )
            if not risk_params.is_valid and "Notional" in risk_params.rejection_reason:
                boosted_usage = self._compute_boosted_capital_usage_for_min_notional(
                    total_capital=portfolio_tool.capital,
                    available_capital=portfolio_tool.available_capital,
                    ai_capital_usage=ai_decision.capital_usage,
                    leverage=risk_tool.max_leverage,
                )
                fake_sim = SimulationResult(
                    direction=final_direction,
                    winrate=sim.winrate,
                    expected_profit_pct=sim.expected_profit_pct,
                    max_drawdown_pct=sim.max_drawdown_pct,
                    sharpe_ratio=sim.sharpe_ratio,
                    mc_median_equity=sim.mc_median_equity,
                    mc_worst_equity=sim.mc_worst_equity,
                    mc_ruin_probability=sim.mc_ruin_probability,
                    recommendation=sim.recommendation,
                    skip_reason=sim.skip_reason,
                )
                if boosted_usage is not None and self._has_high_conviction(fake_sim, ai_decision):
                    logger.info(
                        "[%s] [--force-ai] Ajuste automático de capital_usage: %.1f%% → %.1f%%",
                        symbol,
                        ai_decision.capital_usage * 100,
                        boosted_usage * 100,
                    )
                    risk_params = risk_tool.validate(
                        direction=final_direction,
                        entry_price=current_price,
                        available_capital=available_capital,
                        total_capital=portfolio_tool.capital,
                        capital_usage=boosted_usage,
                    )
            if not risk_params.is_valid:
                logger.info("[%s] [--force-ai] Riesgo rechazó: %s", symbol, risk_params.rejection_reason)
                return

            result = execution_tool.execute(
                symbol=symbol,
                direction=final_direction,
                risk_params=risk_params,
                strategy="AI_FORCED",
                dry_run=self.dry_run,
            )
            if result is not None and result.get("status") == "blocked":
                logger.warning(
                    "[%s] [--force-ai] Omitido: %s",
                    symbol,
                    result.get("reason", "símbolo bloqueado"),
                )
                return
            logger.info("[%s] [--force-ai] Trade ejecutado: %s", symbol, result)
            state.add_log(f"[IA force] TRADE EJECUTADO {symbol} {final_direction} | {result}")

    def _compute_boosted_capital_usage_for_min_notional(
        self,
        total_capital: float,
        available_capital: float,
        ai_capital_usage: float,
        leverage: int,
    ) -> Optional[float]:
        """Calcula el capital_usage mínimo para alcanzar notional >= 100 USDT."""
        if total_capital <= 0 or available_capital <= 0 or leverage <= 0:
            return None

        required_capital = self._min_notional_usdt / leverage
        max_capital = min(available_capital, total_capital * risk_tool.max_capital_pct)
        if max_capital < required_capital:
            return None

        min_usage_required = required_capital / total_capital
        base_usage = ai_capital_usage if ai_capital_usage > 0 else risk_tool.max_capital_pct
        boosted_usage = max(base_usage, min_usage_required)
        return min(boosted_usage, risk_tool.max_capital_pct)

    @staticmethod
    def _has_high_conviction(sim: SimulationResult, ai_decision: AIDecision) -> bool:
        """Filtro extra para permitir subir capital solo con señal robusta."""
        return (
            ai_decision.confidence >= 0.70
            and sim.winrate >= 0.55
            and sim.expected_profit_pct > 0
            and sim.max_drawdown_pct <= 2.0
            and sim.mc_ruin_probability <= 0.20
        )

    # ── Hard rules algorítmicas (sin IA) ─────────────────────────────────────

    def _check_hard_rules(
        self,
        symbol: str,
        direction: str,
        indicators: "Indicators",
        sim: "SimulationResult",
        funding_rate: float = 0.0,
        strategy: str = "",
    ) -> "Tuple[bool, str]":
        """
        Valida las hard rules numéricas sin depender de la IA.
        Retorna (bloqueado: bool, razón: str).
        """
        # 1. RSI extremo en SHORT → riesgo de rebote inminente
        if direction == "SHORT" and indicators.rsi < 22:
            return True, f"RSI={indicators.rsi:.1f} < 22 en SHORT — oversold extremo, riesgo de rebote"

        # 2. RSI extremo en LONG → riesgo de reversión
        if direction == "LONG" and indicators.rsi > 78:
            return True, f"RSI={indicators.rsi:.1f} > 78 en LONG — overbought, riesgo de reversión"

        # 3. Winrate mínimo (simulación ya lo filtra, pero refuerzo aquí)
        if sim.winrate < 0.45:
            return True, f"Winrate={sim.winrate:.1%} < 45% — simulación insuficiente"

        # 4. Probabilidad de ruina
        if sim.mc_ruin_probability > 0.20:
            return True, f"Ruin probability={sim.mc_ruin_probability:.1%} > 20%"

        # 5. Dirección opuesta a la tendencia SMA
        # Excepción controlada: permitir BREAKOUT contra SMA solo si la simulación
        # es suficientemente sólida (evita bloquear rupturas válidas de reversión).
        breakout_countertrend_ok = (
            strategy == "BREAKOUT"
            and sim.winrate >= 0.56
            and sim.expected_profit_pct > 0
            and sim.mc_ruin_probability <= 0.18
        )

        pullback_countertrend_ok = (
            strategy == "PULLBACK"
            and indicators.price > indicators.sma20
            and indicators.rsi >= 55
            and indicators.macd_hist > 0
            and sim.winrate >= 0.56
            and sim.expected_profit_pct > 0
            and sim.mc_ruin_probability <= 0.16
        )

        if (
            direction == "LONG"
            and indicators.sma20 < indicators.sma50
            and not (breakout_countertrend_ok or pullback_countertrend_ok)
        ):
            return True, f"SMA20={indicators.sma20:.2f} < SMA50={indicators.sma50:.2f} — tendencia BEARISH, no LONG"

        pullback_countertrend_ok = (
            strategy == "PULLBACK"
            and indicators.price < indicators.sma20
            and indicators.rsi <= 52
            and indicators.macd_hist < 0
            and sim.winrate >= 0.56
            and sim.expected_profit_pct > 0
            and sim.mc_ruin_probability <= 0.16
        )

        if (
            direction == "SHORT"
            and indicators.sma20 > indicators.sma50
            and not (breakout_countertrend_ok or pullback_countertrend_ok)
        ):
            return True, f"SMA20={indicators.sma20:.2f} > SMA50={indicators.sma50:.2f} — tendencia BULLISH, no SHORT"

        # 6. Funding rate extremo: evita pagar caro por mantener la posición
        FUNDING_LONG_BLOCK  = 0.05   # 0.05 % por funding period → mercado muy apalancado alcista
        FUNDING_SHORT_BLOCK = -0.05  # -0.05 % → mercado muy apalancado bajista
        if direction == "LONG" and funding_rate > FUNDING_LONG_BLOCK:
            return True, (
                f"Funding rate {funding_rate:.4f}% > {FUNDING_LONG_BLOCK}% — "
                "mercado sobre-apalancado alcista, evitar LONG"
            )
        if direction == "SHORT" and funding_rate < FUNDING_SHORT_BLOCK:
            return True, (
                f"Funding rate {funding_rate:.4f}% < {FUNDING_SHORT_BLOCK}% — "
                "mercado sobre-apalancado bajista, evitar SHORT"
            )

        return False, ""

    def market_overview_adjust(self, all_market_data: dict, state: AgentState) -> None:
        """
        Tincho1 analiza las condiciones globales del mercado y ajusta
        los parámetros del agente si lo considera necesario.
        Se llama una vez por ciclo (o cada N ciclos) desde _run_cycle().
        """
        from ai.decision_prompt import build_market_overview_prompt

        prompt = build_market_overview_prompt(
            all_market_data=all_market_data,
            dynamic_params=parameters_manager.params,
            portfolio_state=portfolio_tool.get_state_dict(),
        )
        result = llm_client.market_overview(prompt)
        if result is None:
            return

        adj = result.get("parameter_adjustments")
        if adj and isinstance(adj, dict):
            changed = parameters_manager.apply_adjustments(
                adj,
                reason=f"Tincho1 market overview: {result.get('reasoning', '')[:80]}",
            )
            if changed:
                state.add_log(
                    f"Tincho1 ajustó parámetros globales: {adj} | {result.get('reasoning', '')[:80]}"
                )
                logger.info("🌍 Tincho1 ajustó parámetros: %s", adj)
        else:
            logger.debug("🌍 Tincho1 market overview: sin cambios de parámetros")

    def _log_execution(
        self, symbol, direction, signal, sim, ai_decision, risk_params, result
    ) -> None:
        """Persiste el log completo de ejecución en MongoDB."""
        log_data = {
            "symbol": symbol,
            "direction": direction,
            "signal": signal.signal,
            "strategy": signal.strategy,
            "signal_confidence": signal.confidence,
            "signal_reason": signal.reason,
            "simulation": {
                "winrate": sim.winrate,
                "expected_profit_pct": sim.expected_profit_pct,
                "max_drawdown_pct": sim.max_drawdown_pct,
                "recommendation": sim.recommendation,
            },
            "ai_decision": {
                "trade": ai_decision.trade,
                "confidence": ai_decision.confidence,
                "capital_usage": ai_decision.capital_usage,
                "reasoning": ai_decision.reasoning,
            },
            "risk": {
                "quantity": risk_params.quantity,
                "capital_to_use": risk_params.capital_to_use,
                "stop_loss": risk_params.stop_loss_price,
                "take_profit": risk_params.take_profit_price,
            },
            "execution_result": result,
            "portfolio_after": portfolio_tool.get_state_dict(),
        }
        trade_repository.save_execution_log(log_data)

    def _close_position_from_tool(self, symbol: str, reason: str) -> Tuple[bool, str]:
        """Cierra una posición abierta solicitada por tool calling de la IA."""
        if not symbol:
            return False, "close_position inválido: símbolo vacío"

        pos = portfolio_tool.positions.get(symbol)
        if pos is None:
            return False, f"No hay posición abierta en {symbol}"

        current_price = pos.entry_price
        try:
            ticker = order_manager._client.safe_call(
                order_manager._client.client.futures_symbol_ticker,
                symbol=symbol,
            )
            current_price = float(ticker["price"])
        except Exception as exc:
            logger.warning("[%s] close_position tool: no se pudo obtener ticker (%s)", symbol, exc)

        if not self.dry_run:
            try:
                side = "BUY" if pos.direction == "LONG" else "SELL"
                order_manager.close_position(symbol, side, pos.quantity)
            except Exception as exc:
                return False, f"Error cerrando en exchange: {exc}"

        trade = portfolio_tool.close_position(symbol, current_price, strategy=f"AI_CLOSE:{reason[:40]}")
        if trade is None:
            return False, f"No se pudo cerrar posición en {symbol}"

        return True, f"Posición cerrada en {symbol} por IA ({reason})"


# Instancia global (dry_run se sobreescribe al iniciar el agente)
decision_engine = DecisionEngine(dry_run=True)
