"""
Simulation - Monte Carlo
==========================
Genera N simulaciones aleatorias sobre la distribución de retornos históricos.
Calcula intervalos de confianza y riesgo de ruina.
"""

import numpy as np
from dataclasses import dataclass
from typing import List, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


@dataclass
class MonteCarloResult:
    """Resultado de la simulación de Monte Carlo."""
    num_simulations: int
    num_periods: int
    median_return: float
    mean_return: float
    std_return: float
    percentile_5: float  # Peor caso (5%)
    percentile_25: float
    percentile_75: float
    percentile_95: float  # Mejor caso (95%)
    risk_of_ruin: float  # Probabilidad de perder > 50% del capital
    probability_profit: float  # Probabilidad de terminar con ganancia
    max_drawdown_mean: float

    def to_dict(self) -> dict:
        return {
            "num_simulations": self.num_simulations,
            "num_periods": self.num_periods,
            "median_return": round(self.median_return, 4),
            "mean_return": round(self.mean_return, 4),
            "std_return": round(self.std_return, 4),
            "percentile_5": round(self.percentile_5, 4),
            "percentile_25": round(self.percentile_25, 4),
            "percentile_75": round(self.percentile_75, 4),
            "percentile_95": round(self.percentile_95, 4),
            "risk_of_ruin": round(self.risk_of_ruin, 4),
            "probability_profit": round(self.probability_profit, 4),
            "max_drawdown_mean": round(self.max_drawdown_mean, 4),
        }


class MonteCarloSimulator:
    """
    Simulador de Monte Carlo para evaluar el riesgo de la estrategia.
    
    Toma los retornos históricos de los trades y genera múltiples
    escenarios futuros para estimar el rango de resultados posibles.
    """

    def __init__(self, num_simulations: int = None):
        self.num_simulations = num_simulations or settings.MONTE_CARLO_SIMULATIONS

    def simulate(
        self,
        trade_returns: List[float],
        initial_capital: float = None,
        num_periods: int = 30,
    ) -> MonteCarloResult:
        """
        Ejecuta la simulación de Monte Carlo.
        
        Args:
            trade_returns: Lista de retornos porcentuales de trades históricos.
                          Ej: [0.02, -0.01, 0.05, -0.03, ...]
            initial_capital: Capital inicial (default desde settings).
            num_periods: Número de periodos a simular (default 30).
            
        Returns:
            MonteCarloResult con todas las métricas.
        """
        if initial_capital is None:
            initial_capital = settings.INITIAL_CAPITAL

        if not trade_returns or len(trade_returns) < 3:
            logger.warning("Retornos insuficientes para Monte Carlo, usando defaults")
            trade_returns = [0.0]  # Sin información, asumir 0%

        returns_array = np.array(trade_returns)
        mean_return = np.mean(returns_array)
        std_return = np.std(returns_array)

        logger.info(
            f"🎲 Iniciando Monte Carlo: {self.num_simulations} simulaciones, "
            f"{num_periods} periodos, mean_ret={mean_return:.4f}, std={std_return:.4f}"
        )

        # Generar simulaciones
        final_capitals = np.zeros(self.num_simulations)
        max_drawdowns = np.zeros(self.num_simulations)

        for sim in range(self.num_simulations):
            # Generar retornos aleatorios basados en la distribución histórica
            sim_returns = np.random.normal(mean_return, std_return, num_periods)
            
            # Calcular equity curve
            capital = initial_capital
            peak = capital
            max_dd = 0.0

            for ret in sim_returns:
                capital *= (1 + ret)
                capital = max(capital, 0)  # No puede ser negativo

                if capital > peak:
                    peak = capital
                if peak > 0:
                    dd = (peak - capital) / peak
                    max_dd = max(max_dd, dd)

            final_capitals[sim] = capital
            max_drawdowns[sim] = max_dd

        # Calcular retornos finales como porcentaje
        final_returns = (final_capitals - initial_capital) / initial_capital

        # Estadísticas
        result = MonteCarloResult(
            num_simulations=self.num_simulations,
            num_periods=num_periods,
            median_return=float(np.median(final_returns)),
            mean_return=float(np.mean(final_returns)),
            std_return=float(np.std(final_returns)),
            percentile_5=float(np.percentile(final_returns, 5)),
            percentile_25=float(np.percentile(final_returns, 25)),
            percentile_75=float(np.percentile(final_returns, 75)),
            percentile_95=float(np.percentile(final_returns, 95)),
            risk_of_ruin=float(np.mean(final_returns < -0.5)),  # Perder > 50%
            probability_profit=float(np.mean(final_returns > 0)),
            max_drawdown_mean=float(np.mean(max_drawdowns)),
        )

        logger.info(
            f"✅ Monte Carlo completado: median_ret={result.median_return:.2%}, "
            f"prob_profit={result.probability_profit:.2%}, "
            f"risk_ruin={result.risk_of_ruin:.2%}"
        )

        return result
