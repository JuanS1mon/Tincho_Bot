"""
simulation/monte_carlo.py
==========================
Simulación Monte Carlo para estimar la distribución de resultados
de una estrategia, dado un histórico de retornos por trade.

Genera N simulaciones del equity curve para estimar:
  - Profit esperado en el percentil 50
  - Peor escenario (percentil 5)
  - Probabilidad de ruina (equity < 50% del capital inicial)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from config.logger import trading_logger as logger


@dataclass
class MonteCarloResult:
    simulations: int
    median_final_equity: float      # percentil 50 al final de todas las simulaciones
    worst_case_equity: float        # percentil 5 (escenario adverso)
    best_case_equity: float         # percentil 95
    ruin_probability: float         # % de simulaciones donde equity < 50% del inicial
    expected_profit_pct: float      # ganancia esperada mediana en %


class MonteCarlo:
    """Simula distribución de resultados por Monte Carlo."""

    def __init__(self, n_simulations: int = 500, n_trades: int = 20) -> None:
        self.n_simulations = n_simulations
        self.n_trades = n_trades

    def run(
        self,
        winrate: float,
        avg_profit_pct: float,
        avg_loss_pct: float,
        initial_equity: float = 1.0,
    ) -> MonteCarloResult:
        """
        Corre N simulaciones de 'n_trades' operaciones.
        Cada trade: con probabilidad `winrate` gana `avg_profit_pct%`,
        de lo contrario pierde `avg_loss_pct%`.
        """
        if winrate <= 0 or winrate >= 1:
            return MonteCarloResult(0, initial_equity, initial_equity, initial_equity, 1.0, 0.0)

        profit_mult = 1 + avg_profit_pct / 100
        loss_mult = 1 - avg_loss_pct / 100

        rng = np.random.default_rng(seed=42)
        # Matriz: (n_simulations, n_trades) de True/False para win
        wins = rng.random((self.n_simulations, self.n_trades)) < winrate
        multipliers = np.where(wins, profit_mult, loss_mult)

        # Equity final de cada simulación (producto acumulado)
        final_equities = initial_equity * np.prod(multipliers, axis=1)

        median_eq = float(np.median(final_equities))
        worst_eq = float(np.percentile(final_equities, 5))
        best_eq = float(np.percentile(final_equities, 95))
        ruin_prob = float((final_equities < initial_equity * 0.5).mean())
        expected_profit_pct = (median_eq - initial_equity) / initial_equity * 100

        logger.debug(
            "MonteCarlo: mediana_eq=%.4f worst=%.4f ruin_prob=%.2f%%",
            median_eq, worst_eq, ruin_prob * 100,
        )

        return MonteCarloResult(
            simulations=self.n_simulations,
            median_final_equity=round(median_eq, 4),
            worst_case_equity=round(worst_eq, 4),
            best_case_equity=round(best_eq, 4),
            ruin_probability=round(ruin_prob, 4),
            expected_profit_pct=round(expected_profit_pct, 4),
        )


# Instancia global
monte_carlo = MonteCarlo()
