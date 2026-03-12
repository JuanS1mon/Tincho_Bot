"""
tests/test_indicators.py
========================
Pruebas del cálculo de indicadores técnicos (SMA, RSI, MACD).
No requiere conexión a Binance ni MongoDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import numpy as np
import pandas as pd

from tools.indicator_tool import IndicatorTool, Indicators


def _make_df(prices: list, volume: float = 1000.0) -> pd.DataFrame:
    """Crea un DataFrame OHLCV mínimo a partir de una lista de precios close."""
    n = len(prices)
    prices = [float(p) for p in prices]
    return pd.DataFrame({
        "open":   prices,
        "high":   [p * 1.001 for p in prices],
        "low":    [p * 0.999 for p in prices],
        "close":  prices,
        "volume": [volume] * n,
    })


tool = IndicatorTool()


class TestIndicatorTool:

    def test_retorna_none_si_menos_de_50_velas(self):
        df = _make_df(list(range(1, 49)))
        assert tool.calculate(df) is None

    def test_retorna_none_con_exactamente_49_velas(self):
        df = _make_df([100.0] * 49)
        assert tool.calculate(df) is None

    def test_retorna_indicators_con_50_velas(self):
        df = _make_df([100.0 + i * 0.1 for i in range(50)])
        result = tool.calculate(df)
        assert result is not None
        assert isinstance(result, Indicators)

    def test_sma20_correcto(self):
        # Precio constante → SMA20 == precio
        df = _make_df([200.0] * 60)
        ind = tool.calculate(df)
        assert abs(ind.sma20 - 200.0) < 0.01

    def test_sma50_correcto(self):
        df = _make_df([500.0] * 60)
        ind = tool.calculate(df)
        assert abs(ind.sma50 - 500.0) < 0.01

    def test_rsi_rango_valido(self):
        # RSI siempre debe estar entre 0 y 100
        prices = [100 + (i % 10) * 2 for i in range(80)]
        df = _make_df(prices)
        ind = tool.calculate(df)
        assert 0 <= ind.rsi <= 100

    def test_rsi_tendencia_alcista_alto(self):
        # Precios siempre subiendo → RSI cercano a 100
        prices = [float(50 + i) for i in range(80)]
        df = _make_df(prices)
        ind = tool.calculate(df)
        assert ind.rsi > 70, f"RSI esperado > 70 para tendencia alcista, got {ind.rsi}"

    def test_rsi_tendencia_bajista_bajo(self):
        # Precios siempre bajando → RSI cercano a 0
        prices = [float(100 - i * 0.5) for i in range(80)]
        df = _make_df(prices)
        ind = tool.calculate(df)
        assert ind.rsi < 40, f"RSI esperado < 40 para tendencia bajista, got {ind.rsi}"

    def test_precio_es_ultimo_close(self):
        prices = [float(i) for i in range(1, 61)]
        df = _make_df(prices)
        ind = tool.calculate(df)
        assert abs(ind.price - 60.0) < 0.01

    def test_volume_avg_correcto(self):
        df = _make_df([100.0] * 60, volume=2500.0)
        ind = tool.calculate(df)
        assert abs(ind.volume_avg - 2500.0) < 1.0

    def test_macd_es_float(self):
        prices = [100 + np.sin(i * 0.3) * 5 for i in range(80)]
        df = _make_df(prices)
        ind = tool.calculate(df)
        assert isinstance(ind.macd, float)
        assert isinstance(ind.macd_signal, float)
        assert isinstance(ind.macd_hist, float)
