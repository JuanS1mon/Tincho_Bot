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

        # ── 2. Consultar IA ───────────────────────────────────────────────────
        logger.info("[%s] Consultando IA...", symbol)
        user_prompt = build_decision_prompt(
            all_market_data,
            sim,
            dynamic_params=parameters_manager.params,
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
        decision_word = "OPERAR" if ai_decision.trade else "NO OPERAR"
        logger.info(
            "[%s] [IA] %s | conf=%.0f%% | %s",
            symbol, decision_word, ai_decision.confidence * 100, ai_decision.reasoning,
        )
        state.add_log(
            f"[IA] {decision_word} conf={ai_decision.confidence:.0%} | {ai_decision.reasoning}"
        )

        if not ai_decision.trade:
            reason = f"IA rechazó el trade: {ai_decision.reasoning}"
            logger.info("[%s] %s", symbol, reason)
            # Aplicar ajustes de parámetros aunque no haya trade
            if ai_decision.parameter_adjustments:
                parameters_manager.apply_adjustments(
                    ai_decision.parameter_adjustments,
                    reason=f"No-trade cycle: {ai_decision.reasoning}",
                )
            return False, reason

        # Verificar coherencia señal local vs IA
        if ai_decision.symbol != symbol or ai_decision.direction != direction:
            logger.warning(
                "[%s] IA sugiere %s/%s pero señal local es %s/%s — usando señal local",
                symbol, ai_decision.symbol, ai_decision.direction, symbol, direction,
            )

        # ── 3. Validar riesgo ─────────────────────────────────────────────────
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

        # ── 4. Aplicar ajustes de parámetros sugeridos por la IA ─────────────
        if ai_decision.parameter_adjustments:
            parameters_manager.apply_adjustments(
                ai_decision.parameter_adjustments,
                reason=f"Trade approved: {ai_decision.reasoning}",
            )
            state.add_log(f"Parámetros ajustados por IA: {ai_decision.parameter_adjustments}")

        # ── 5. Ejecutar trade ─────────────────────────────────────────────────
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
        Consulta la IA solo para análisis/registro, sin ejecutar ningún trade.
        Usado con --force-ai para observar el razonamiento de la IA en pruebas.
        """
        from tools.simulation_tool import simulation_tool
        logger.info("[%s] [--force-ai] Consultando IA sin señal activa...", symbol)

        # Simulación neutral para dar contexto a la IA (dirección LONG como referencia)
        sim = simulation_tool.simulate(df, "LONG", portfolio_tool.capital)

        user_prompt = build_decision_prompt(
            all_market_data,
            sim,
            dynamic_params=parameters_manager.params,
        )
        ai_decision = llm_client.decide(user_prompt)

        if ai_decision is None:
            logger.warning("[%s] [--force-ai] IA no respondió", symbol)
            return

        decision_word = "OPERAR" if ai_decision.trade else "NO OPERAR"
        logger.info(
            "[%s] [IA] %s | conf=%.0f%% | %s",
            symbol, decision_word, ai_decision.confidence * 100, ai_decision.reasoning,
        )
        state.add_log(
            f"[IA force] {decision_word} conf={ai_decision.confidence:.0%} | {ai_decision.reasoning}"
        )

        # Aplicar ajustes de parámetros si la IA los propone
        if ai_decision.parameter_adjustments:
            parameters_manager.apply_adjustments(
                ai_decision.parameter_adjustments,
                reason=f"force-ai cycle: {ai_decision.reasoning}",
            )

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
