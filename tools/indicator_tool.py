"""
tools/indicator_tool.py
=======================
Calcula indicadores técnicos sobre un DataFrame OHLCV:
  - SMA20, SMA50
  - RSI (14 períodos)
  - MACD (12, 26, 9)
  - Volumen promedio (20 períodos)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd
import ta


@dataclass
class Indicators:
    sma20: float
    sma50: float
    rsi: float
    macd: float
    macd_signal: float
    macd_hist: float
    volume_avg: float
    # Precio actual (último close)
    price: float


class IndicatorTool:
    """Calcula indicadores técnicos sobre DataFrame OHLCV."""

    def calculate(self, df: pd.DataFrame) -> Optional[Indicators]:
        """
        Recibe un DataFrame con columnas [open, high, low, close, volume]
        y retorna el último valor de cada indicador calculado.
        Retorna None si no hay suficientes datos.
        """
        if len(df) < 50:
            return None

        close = df["close"]
        volume = df["volume"]

        # ── SMA ──────────────────────────────────────────────────────────────
        sma20_series = ta.trend.sma_indicator(close, window=20)
        sma50_series = ta.trend.sma_indicator(close, window=50)

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_series = ta.momentum.rsi(close, window=14)

        # ── MACD ──────────────────────────────────────────────────────────────
        macd_obj = ta.trend.MACD(close, window_slow=26, window_fast=12, window_sign=9)
        macd_line = macd_obj.macd()
        macd_signal = macd_obj.macd_signal()
        macd_hist = macd_obj.macd_diff()

        # ── Volume average (20 períodos) ──────────────────────────────────────
        vol_avg = volume.rolling(window=20).mean()

        return Indicators(
            sma20=round(float(sma20_series.iloc[-1]), 4),
            sma50=round(float(sma50_series.iloc[-1]), 4),
            rsi=round(float(rsi_series.iloc[-1]), 2),
            macd=round(float(macd_line.iloc[-1]), 6),
            macd_signal=round(float(macd_signal.iloc[-1]), 6),
            macd_hist=round(float(macd_hist.iloc[-1]), 6),
            volume_avg=round(float(vol_avg.iloc[-1]), 2),
            price=round(float(close.iloc[-1]), 4),
        )


# Instancia global
indicator_tool = IndicatorTool()
