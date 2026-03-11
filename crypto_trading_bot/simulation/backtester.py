"""
Simulation - Backtester
========================
Ejecuta la estrategia de trading sobre datos históricos (30 días).
Calcula métricas: profit, drawdown, win_rate, sharpe_ratio.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from config.logger import get_logger
from config.settings import settings
from indicators.rsi import calculate_rsi
from indicators.macd import calculate_macd
from indicators.sma import calculate_sma
from indicators.ema import calculate_ema
from indicators.volatility import calculate_volatility

logger = get_logger(__name__)


class BacktestResult:
    """Resultado de un backtesting."""

    def __init__(self):
        self.trades: List[dict] = []
        self.equity_curve: List[float] = []
        self.initial_capital: float = 0
        self.final_capital: float = 0

    @property
    def total_trades(self) -> int:
        return len(self.trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for t in self.trades if t["pnl"] > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for t in self.trades if t["pnl"] <= 0)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.winning_trades / self.total_trades

    @property
    def profit(self) -> float:
        return self.final_capital - self.initial_capital

    @property
    def profit_percent(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.profit / self.initial_capital) * 100

    @property
    def max_drawdown(self) -> float:
        """Calcula el máximo drawdown de la equity curve."""
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0]
        max_dd = 0.0
        for value in self.equity_curve:
            if value > peak:
                peak = value
            dd = (peak - value) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        """Calcula el Sharpe Ratio (asumiendo risk-free rate = 0)."""
        if len(self.equity_curve) < 2:
            return 0.0
        returns = pd.Series(self.equity_curve).pct_change().dropna()
        if returns.std() == 0:
            return 0.0
        # Anualizado (asumiendo datos horarios: 24h * 365)
        return (returns.mean() / returns.std()) * np.sqrt(8760)

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "profit": round(self.profit, 2),
            "profit_percent": round(self.profit_percent, 2),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "initial_capital": self.initial_capital,
            "final_capital": round(self.final_capital, 2),
        }


class Backtester:
    """
    Motor de backtesting para la estrategia de trading.
    Simula la ejecución de la estrategia sobre datos históricos.
    """

    def __init__(self, initial_capital: float = None):
        self.initial_capital = initial_capital or settings.INITIAL_CAPITAL

    def run(
        self,
        klines: Dict[str, pd.DataFrame],
        allocation: Dict[str, float] = None,
    ) -> BacktestResult:
        """
        Ejecuta el backtest sobre los datos históricos.
        
        Args:
            klines: Diccionario {symbol: DataFrame} con datos de velas.
            allocation: Distribución del capital por activo (default 50/50).
            
        Returns:
            BacktestResult con todas las métricas.
        """
        if allocation is None:
            allocation = {"BTCUSDT": 0.5, "ETHUSDT": 0.5}

        result = BacktestResult()
        result.initial_capital = self.initial_capital
        capital = self.initial_capital

        logger.info(f"🔄 Iniciando backtest con capital={capital:.2f} USDT")

        # Procesar cada símbolo
        for symbol, df in klines.items():
            if df is None or len(df) < 50:
                logger.warning(f"Datos insuficientes para backtest de {symbol}")
                continue

            alloc_pct = allocation.get(symbol, 0.5)
            symbol_capital = capital * alloc_pct
            symbol_trades = self._backtest_symbol(symbol, df, symbol_capital)
            result.trades.extend(symbol_trades)

        # Calcular equity curve y capital final
        capital = self.initial_capital
        result.equity_curve.append(capital)

        for trade in sorted(result.trades, key=lambda t: t["entry_index"]):
            capital += trade["pnl"]
            result.equity_curve.append(capital)

        result.final_capital = capital

        logger.info(
            f"✅ Backtest completado: trades={result.total_trades}, "
            f"win_rate={result.win_rate:.2%}, profit={result.profit:.2f} USDT, "
            f"drawdown={result.max_drawdown:.2%}, sharpe={result.sharpe_ratio:.2f}"
        )

        return result

    def _backtest_symbol(
        self, symbol: str, df: pd.DataFrame, capital: float
    ) -> List[dict]:
        """
        Ejecuta backtest para un símbolo individual.
        Estrategia: compra cuando RSI < 40 y MACD bullish, vende cuando RSI > 65 o stop/take.
        """
        trades = []
        closes = df["close"].astype(float)

        # Calcular indicadores
        rsi = calculate_rsi(closes, period=14)
        macd_line, signal_line, histogram = calculate_macd(closes)
        sma_20 = calculate_sma(closes, period=20)
        sma_50 = calculate_sma(closes, period=50)

        position = None  # None = sin posición, dict = posición abierta
        available = capital

        for i in range(50, len(df)):  # Empezar después de que los indicadores se estabilicen
            current_price = closes.iloc[i]
            current_rsi = rsi.iloc[i] if i < len(rsi) else 50
            current_hist = histogram.iloc[i] if i < len(histogram) else 0
            current_sma20 = sma_20.iloc[i] if i < len(sma_20) else current_price
            current_sma50 = sma_50.iloc[i] if i < len(sma_50) else current_price

            if position is None:
                # --- Señal de COMPRA ---
                buy_signal = (
                    current_rsi < 40
                    and current_hist > 0
                    and current_price > current_sma20
                )

                if buy_signal and available > 10:
                    trade_amount = available * settings.MAX_CAPITAL_PER_TRADE
                    quantity = trade_amount / current_price
                    position = {
                        "symbol": symbol,
                        "entry_price": current_price,
                        "quantity": quantity,
                        "entry_index": i,
                        "stop_loss": current_price * (1 - settings.STOP_LOSS),
                        "take_profit": current_price * (1 + settings.TAKE_PROFIT),
                    }
                    available -= trade_amount

            else:
                # --- Señal de VENTA ---
                hit_stop = current_price <= position["stop_loss"]
                hit_take = current_price >= position["take_profit"]
                sell_signal = current_rsi > 65 or current_hist < 0

                if hit_stop or hit_take or sell_signal:
                    pnl = (current_price - position["entry_price"]) * position["quantity"]
                    available += (position["quantity"] * current_price)

                    trade_result = {
                        "symbol": symbol,
                        "entry_price": position["entry_price"],
                        "exit_price": current_price,
                        "quantity": position["quantity"],
                        "pnl": pnl,
                        "entry_index": position["entry_index"],
                        "exit_index": i,
                        "reason": "stop_loss" if hit_stop else "take_profit" if hit_take else "signal",
                    }
                    trades.append(trade_result)
                    position = None

        # Cerrar posición abierta al final del periodo
        if position:
            final_price = closes.iloc[-1]
            pnl = (final_price - position["entry_price"]) * position["quantity"]
            trades.append({
                "symbol": symbol,
                "entry_price": position["entry_price"],
                "exit_price": final_price,
                "quantity": position["quantity"],
                "pnl": pnl,
                "entry_index": position["entry_index"],
                "exit_index": len(df) - 1,
                "reason": "end_of_period",
            })

        return trades
