"""
tools/simulation_tool.py
=========================
Wrapper que unifica Backtester + MonteCarlo en un único resultado
para que el DecisionEngine lo consuma antes de consultar a la IA.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from simulation.backtester import backtester, BacktestResult
from simulation.monte_carlo import monte_carlo, MonteCarloResult
from config.settings import settings
from config.logger import trading_logger as logger


@dataclass
class SimulationResult:
    direction: str
    winrate: float
    expected_profit_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    mc_median_equity: float
    mc_worst_equity: float
    mc_ruin_probability: float
    recommendation: str    # PROCEED | SKIP
    skip_reason: str


class SimulationTool:
    """Ejecuta backtest + Monte Carlo y decide si proceder con el trade."""

    def __init__(self) -> None:
        self.min_winrate = settings.min_winrate

    def simulate(
        self,
        df: pd.DataFrame,
        direction: str,
        capital: float,
        sl_pct: Optional[float] = None,
        tp_pct: Optional[float] = None,
    ) -> SimulationResult:
        """
        Ejecuta ambas simulaciones sobre el DataFrame OHLCV.

        sl_pct/tp_pct: parámetros dinámicos actuales; si no se pasan
        usa los values del .env via settings.
        Retorna SimulationResult con recomendación PROCEED / SKIP.
        """
        try:
            bt: BacktestResult = backtester.run(df, direction, sl_pct=sl_pct, tp_pct=tp_pct)
            mc: MonteCarloResult = monte_carlo.run(
                winrate=bt.winrate,
                avg_profit_pct=bt.avg_profit_pct,
                avg_loss_pct=bt.avg_loss_pct,
                initial_equity=capital,
            )

            # Decisión: no operar si winrate < mínimo
            if bt.winrate < self.min_winrate:
                reason = f"Winrate {bt.winrate*100:.1f}% < mínimo {self.min_winrate*100:.0f}%"
                recommendation = "SKIP"
            elif mc.ruin_probability > 0.3:
                reason = f"Probabilidad de ruina {mc.ruin_probability*100:.1f}% > 30%"
                recommendation = "SKIP"
            else:
                reason = ""
                recommendation = "PROCEED"

            result = SimulationResult(
                direction=direction,
                winrate=bt.winrate,
                expected_profit_pct=bt.expected_profit_pct,
                max_drawdown_pct=bt.max_drawdown_pct,
                sharpe_ratio=bt.sharpe_ratio,
                mc_median_equity=mc.median_final_equity,
                mc_worst_equity=mc.worst_case_equity,
                mc_ruin_probability=mc.ruin_probability,
                recommendation=recommendation,
                skip_reason=reason,
            )

            logger.info(
                "Simulación %s: winrate=%.1f%% profit=%.2f%% drawdown=%.2f%% → %s",
                direction, bt.winrate * 100, bt.expected_profit_pct,
                bt.max_drawdown_pct, recommendation,
            )
            return result

        except Exception as exc:
            from config.logger import error_logger
            error_logger.error("SimulationTool.simulate error: %s", exc)
            return SimulationResult(
                direction=direction,
                winrate=0, expected_profit_pct=0, max_drawdown_pct=0,
                sharpe_ratio=0, mc_median_equity=capital,
                mc_worst_equity=capital, mc_ruin_probability=1.0,
                recommendation="SKIP",
                skip_reason=f"Error en simulación: {exc}",
            )


# Instancia global
simulation_tool = SimulationTool()
