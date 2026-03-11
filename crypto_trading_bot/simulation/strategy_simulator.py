"""
Simulation - Strategy Simulator
=================================
Orquesta Backtester + Monte Carlo.
Gate obligatorio: si win_rate < 55% → NO operar.
"""

from typing import Dict, Optional

import pandas as pd

from config.logger import get_logger
from config.settings import settings
from simulation.backtester import Backtester, BacktestResult
from simulation.monte_carlo import MonteCarloSimulator, MonteCarloResult

logger = get_logger(__name__)


class SimulationResult:
    """Resultado combinado de backtesting + Monte Carlo."""

    def __init__(
        self,
        backtest: BacktestResult,
        monte_carlo: MonteCarloResult,
    ):
        self.backtest = backtest
        self.monte_carlo = monte_carlo

    @property
    def approved(self) -> bool:
        """
        Gate obligatorio: la estrategia se aprueba SOLO si:
          - win_rate >= MIN_WIN_RATE (55% por defecto)
          - sharpe_ratio > 0 (rendimiento positivo ajustado por riesgo)
        """
        min_wr = settings.MIN_WIN_RATE
        return (
            self.backtest.win_rate >= min_wr
            and self.backtest.sharpe_ratio > 0
        )

    @property
    def reason(self) -> str:
        """Razón de aprobación o rechazo."""
        if self.approved:
            return (
                f"Simulación APROBADA: win_rate={self.backtest.win_rate:.2%}, "
                f"sharpe={self.backtest.sharpe_ratio:.2f}, "
                f"mc_prob_profit={self.monte_carlo.probability_profit:.2%}"
            )
        reasons = []
        if self.backtest.win_rate < settings.MIN_WIN_RATE:
            reasons.append(
                f"win_rate={self.backtest.win_rate:.2%} < {settings.MIN_WIN_RATE:.2%}"
            )
        if self.backtest.sharpe_ratio <= 0:
            reasons.append(f"sharpe_ratio={self.backtest.sharpe_ratio:.2f} <= 0")
        return f"Simulación RECHAZADA: {', '.join(reasons)}"

    def to_dict(self) -> dict:
        """Serializa para almacenamiento y envío a IA."""
        return {
            "approved": self.approved,
            "reason": self.reason,
            # Backtest
            "win_rate": round(self.backtest.win_rate, 4),
            "profit": round(self.backtest.profit, 2),
            "profit_percent": round(self.backtest.profit_percent, 2),
            "max_drawdown": round(self.backtest.max_drawdown, 4),
            "sharpe_ratio": round(self.backtest.sharpe_ratio, 4),
            "total_trades": self.backtest.total_trades,
            # Monte Carlo
            "mc_median_return": round(self.monte_carlo.median_return, 4),
            "mc_mean_return": round(self.monte_carlo.mean_return, 4),
            "mc_risk_of_ruin": round(self.monte_carlo.risk_of_ruin, 4),
            "mc_probability_profit": round(self.monte_carlo.probability_profit, 4),
            "mc_percentile_5": round(self.monte_carlo.percentile_5, 4),
            "mc_percentile_95": round(self.monte_carlo.percentile_95, 4),
        }


class StrategySimulator:
    """
    Orquesta las simulaciones antes de permitir el trading.
    Ejecuta backtesting + Monte Carlo y decide si se permite operar.
    """

    def __init__(self):
        self.backtester = Backtester()
        self.monte_carlo = MonteCarloSimulator()

    def run_full_simulation(
        self,
        klines: Dict[str, pd.DataFrame],
        allocation: Dict[str, float] = None,
    ) -> SimulationResult:
        """
        Ejecuta la simulación completa: backtest + Monte Carlo.
        
        Args:
            klines: Datos históricos {symbol: DataFrame}.
            allocation: Distribución del capital por activo.
            
        Returns:
            SimulationResult con el veredicto de aprobación/rechazo.
        """
        logger.info("=" * 60)
        logger.info("🔬 INICIANDO SIMULACIÓN OBLIGATORIA")
        logger.info("=" * 60)

        # --- 1. Backtesting ---
        logger.info("📊 Paso 1/2: Backtesting...")
        backtest_result = self.backtester.run(klines, allocation)

        # --- 2. Monte Carlo ---
        logger.info("🎲 Paso 2/2: Monte Carlo...")

        # Extraer retornos de los trades del backtest
        trade_returns = []
        for trade in backtest_result.trades:
            if trade["entry_price"] > 0:
                ret = (trade["exit_price"] - trade["entry_price"]) / trade["entry_price"]
                trade_returns.append(ret)

        monte_carlo_result = self.monte_carlo.simulate(
            trade_returns=trade_returns,
            initial_capital=settings.INITIAL_CAPITAL,
            num_periods=30,
        )

        # --- Resultado combinado ---
        simulation = SimulationResult(backtest_result, monte_carlo_result)

        if simulation.approved:
            logger.info(f"✅ {simulation.reason}")
        else:
            logger.warning(f"🚫 {simulation.reason}")
            logger.warning("⛔ EL BOT NO OPERARÁ HASTA QUE LA SIMULACIÓN PASE")

        logger.info("=" * 60)
        return simulation
