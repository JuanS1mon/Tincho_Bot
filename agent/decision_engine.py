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
from agent.state_manager import AgentState, SimulationState, AIDecisionState
from agent.parameters_manager import parameters_manager
from storage.trade_repository import trade_repository
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class DecisionEngine:
    """
    Toma una señal de trading y ejecuta el pipeline completo de validación
    antes de decidir si ejecutar o no el trade.
    """

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

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
        blocked, block_reason = self._check_hard_rules(symbol, direction, indicators, sim)
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
        ai_decision: Optional[AIDecision] = llm_client.decide(user_prompt)

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

        # La decisión de trade la toma el código (hard rules ya validadas arriba).
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

        # Capital asignado a este símbolo (50% / 50% del total)
        symbol_allocation = portfolio_tool.symbol_allocation(symbol)
        symbol_available = portfolio_tool.available_capital_for_symbol(symbol)

        current_price = indicators.price
        risk_params: RiskParams = risk_tool.validate(
            direction=direction,
            entry_price=current_price,
            available_capital=symbol_available,
            total_capital=symbol_allocation,
            capital_usage=ai_decision.capital_usage,
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
            risk_params = risk_tool.validate(
                direction=final_direction,
                entry_price=current_price,
                available_capital=portfolio_tool.available_capital_for_symbol(symbol),
                total_capital=portfolio_tool.symbol_allocation(symbol),
                capital_usage=ai_decision.capital_usage,
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
            logger.info("[%s] [--force-ai] Trade ejecutado: %s", symbol, result)
            state.add_log(f"[IA force] TRADE EJECUTADO {symbol} {final_direction} | {result}")

    # ── Hard rules algorítmicas (sin IA) ─────────────────────────────────────

    def _check_hard_rules(
        self,
        symbol: str,
        direction: str,
        indicators: "Indicators",
        sim: "SimulationResult",
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
        if direction == "LONG" and indicators.sma20 < indicators.sma50:
            return True, f"SMA20={indicators.sma20:.2f} < SMA50={indicators.sma50:.2f} — tendencia BEARISH, no LONG"
        if direction == "SHORT" and indicators.sma20 > indicators.sma50:
            return True, f"SMA20={indicators.sma20:.2f} > SMA50={indicators.sma50:.2f} — tendencia BULLISH, no SHORT"

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


# Instancia global (dry_run se sobreescribe al iniciar el agente)
decision_engine = DecisionEngine(dry_run=True)
