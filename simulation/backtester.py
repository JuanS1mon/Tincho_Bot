"""
simulation/backtester.py
========================
Backtest vectorizado sobre datos históricos OHLCV.
Simula la estrategia de pullback/breakout para obtener:
  - Winrate
  - Profit promedio esperado
  - Drawdown máximo
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd
import numpy as np

from config.settings import settings
from config.logger import trading_logger as logger


@dataclass
class BacktestResult:
    total_trades: int
    winning_trades: int
    winrate: float
    avg_profit_pct: float
    avg_loss_pct: float
    expected_profit_pct: float  # winrate*avg_profit - (1-winrate)*avg_loss
    max_drawdown_pct: float
    sharpe_ratio: float


class Backtester:
    """Simula la estrategia sobre datos históricos OHLCV."""

    def __init__(self) -> None:
        self.sl_pct = settings.stop_loss
        self.tp_pct = settings.take_profit

    def run(
        self,
        df: pd.DataFrame,
        direction: str = "LONG",
        sl_pct: Optional[float] = None,
        tp_pct: Optional[float] = None,
    ) -> BacktestResult:
        """
        Simula entradas en cada vela y evalúa si alcanzó TP o SL primero.

        sl_pct/tp_pct permiten usar los parámetros dinámicos actuales
        en lugar de los valores estáticos del .env.
        """
        _sl = sl_pct if sl_pct is not None else self.sl_pct
        _tp = tp_pct if tp_pct is not None else self.tp_pct
        if len(df) < 30:
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0)

        profits: List[float] = []
        equity = [1.0]  # normalizado

        for i in range(len(df) - 1):
            entry = df["close"].iloc[i]

            if direction == "LONG":
                sl = entry * (1 - _sl)
                tp = entry * (1 + _tp)
                next_low = df["low"].iloc[i + 1]
                next_high = df["high"].iloc[i + 1]

                if next_low <= sl:
                    pnl_pct = -_sl
                elif next_high >= tp:
                    pnl_pct = _tp
                else:
                    # Cierre al precio de cierre de la siguiente vela
                    pnl_pct = (df["close"].iloc[i + 1] - entry) / entry
            else:  # SHORT
                sl = entry * (1 + _sl)
                tp = entry * (1 - _tp)
                next_high = df["high"].iloc[i + 1]
                next_low = df["low"].iloc[i + 1]

                if next_high >= sl:
                    pnl_pct = -_sl
                elif next_low <= tp:
                    pnl_pct = _tp
                else:
                    pnl_pct = (entry - df["close"].iloc[i + 1]) / entry

            profits.append(pnl_pct)
            equity.append(equity[-1] * (1 + pnl_pct))

        if not profits:
            return BacktestResult(0, 0, 0, 0, 0, 0, 0, 0)

        profits_arr = np.array(profits)
        wins = profits_arr[profits_arr > 0]
        losses = profits_arr[profits_arr <= 0]

        total = len(profits_arr)
        win_count = len(wins)
        winrate = win_count / total if total > 0 else 0

        avg_profit = float(wins.mean()) if len(wins) > 0 else 0
        avg_loss = float(abs(losses.mean())) if len(losses) > 0 else 0
        expected = winrate * avg_profit - (1 - winrate) * avg_loss

        # Drawdown máximo
        equity_arr = np.array(equity)
        running_max = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - running_max) / running_max
        max_drawdown = float(abs(drawdown.min()))

        # Sharpe simplificado (sin tasa libre de riesgo)
        std = profits_arr.std()
        sharpe = float(profits_arr.mean() / std * np.sqrt(252)) if std > 0 else 0

        logger.debug(
            "Backtest %s: total=%d winrate=%.2f%% expected=%.4f%% drawdown=%.2f%%",
            direction, total, winrate * 100, expected * 100, max_drawdown * 100,
        )

        return BacktestResult(
            total_trades=total,
            winning_trades=win_count,
            winrate=round(winrate, 4),
            avg_profit_pct=round(avg_profit * 100, 4),
            avg_loss_pct=round(avg_loss * 100, 4),
            expected_profit_pct=round(expected * 100, 4),
            max_drawdown_pct=round(max_drawdown * 100, 4),
            sharpe_ratio=round(sharpe, 4),
        )


# Instancia global
backtester = Backtester()
