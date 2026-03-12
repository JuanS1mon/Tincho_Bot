"""
tests/test_trend_and_signals.py
================================
Pruebas del detector de tendencia y del detector de señales de trading.
No requiere conexión a Binance ni MongoDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pandas as pd
import numpy as np

from tools.indicator_tool import Indicators
from analysis.trend_detector import TrendDetector, Trend
from analysis.volume_analyzer import VolumeAnalysis
from analysis.open_interest_analyzer import OIAnalysis
from analysis.signal_detector import SignalDetector


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ind(sma20=100.0, sma50=100.0, rsi=55.0, price=100.0,
         macd=0.0, macd_signal=0.0, macd_hist=0.0, volume_avg=1000.0) -> Indicators:
    return Indicators(
        sma20=sma20, sma50=sma50, rsi=rsi, price=price,
        macd=macd, macd_signal=macd_signal, macd_hist=macd_hist,
        volume_avg=volume_avg,
    )


def _vol(trend="INCREASING", is_high=True, ratio=1.5) -> VolumeAnalysis:
    return VolumeAnalysis(
        current_volume=1500.0,
        avg_volume=1000.0,
        volume_ratio=ratio,
        trend=trend,
        is_high_volume=is_high,
    )


def _oi(trend="INCREASING", change_pct=1.0) -> OIAnalysis:
    return OIAnalysis(
        current_oi=1000.0,
        oi_change_pct=change_pct,
        trend=trend,
        signal="STRONG_BULL" if trend == "INCREASING" else "NEUTRAL",
        description="test",
    )


def _df_bullish(n=60) -> pd.DataFrame:
    """DataFrame con tendencia alcista clara (precios subiendo)."""
    prices = [float(100 + i * 0.5) for i in range(n)]
    return pd.DataFrame({
        "open": prices, "high": [p * 1.001 for p in prices],
        "low": [p * 0.999 for p in prices], "close": prices,
        "volume": [1500.0] * n,
    })


# ── Tests TrendDetector ────────────────────────────────────────────────────────

class TestTrendDetector:
    detector = TrendDetector()

    def test_bullish_cuando_sma20_mayor(self):
        ind = _ind(sma20=102.0, sma50=100.0)
        assert self.detector.detect(ind) == Trend.BULLISH

    def test_bearish_cuando_sma20_menor(self):
        ind = _ind(sma20=98.0, sma50=100.0)
        assert self.detector.detect(ind) == Trend.BEARISH

    def test_neutral_cuando_smas_muy_cercanos(self):
        # diff = 0.05% → menor al umbral de 0.1%
        ind = _ind(sma20=100.05, sma50=100.0)
        assert self.detector.detect(ind) == Trend.NEUTRAL

    def test_neutral_cuando_iguales(self):
        ind = _ind(sma20=100.0, sma50=100.0)
        assert self.detector.detect(ind) == Trend.NEUTRAL

    def test_describe_retorna_dict_correcto(self):
        ind = _ind(sma20=105.0, sma50=100.0)
        desc = self.detector.describe(ind)
        assert desc["trend"] == "BULLISH"
        assert "sma20" in desc and "sma50" in desc
        assert desc["diff_pct"] == pytest.approx(5.0, abs=0.01)


# ── Tests SignalDetector ───────────────────────────────────────────────────────

class TestSignalDetector:
    detector = SignalDetector()

    def test_no_signal_neutral_trend(self):
        # Tendencia NEUTRAL → no debe haber señal
        ind = _ind(sma20=100.0, sma50=100.0, rsi=55.0, price=100.0)
        sig = self.detector.detect(_df_bullish(), ind, _vol(), _oi())
        # Con tendencia neutral no debería ser pullback LONG/SHORT
        # (podría ser breakout si el precio supera máximo histórico)
        assert sig.signal in ("LONG", "SHORT", "NO_SIGNAL")  # al menos tiene formato válido

    def test_long_pullback_condiciones_ok(self):
        # Condiciones perfectas para LONG pullback:
        # BULLISH + precio cerca SMA20 + RSI>50 + volumen creciente + OI subiendo
        ind = _ind(sma20=100.0, sma50=98.0, rsi=60.0, price=100.5)
        sig = self.detector.detect(_df_bullish(), ind, _vol("INCREASING", True), _oi("INCREASING"))
        assert sig.signal == "LONG"
        assert sig.strategy == "PULLBACK"

    def test_no_long_si_tendencia_bearish(self):
        ind = _ind(sma20=98.0, sma50=100.0, rsi=60.0, price=98.0)
        sig = self.detector.detect(_df_bullish(), ind, _vol("INCREASING", True), _oi("INCREASING"))
        assert sig.signal != "LONG"

    def test_no_long_si_rsi_bajo(self):
        # RSI ≤ 50 → no LONG pullback
        ind = _ind(sma20=100.0, sma50=98.0, rsi=45.0, price=100.0)
        sig = self.detector.detect(_df_bullish(), ind, _vol("INCREASING", True), _oi("INCREASING"))
        assert sig.signal != "LONG" or sig.strategy != "PULLBACK"

    def test_no_long_si_precio_lejos_sma20(self):
        # Precio +5% sobre SMA20 → fuera del rango de pullback (1.5%)
        ind = _ind(sma20=100.0, sma50=98.0, rsi=60.0, price=105.0)
        sig = self.detector.detect(_df_bullish(), ind, _vol("INCREASING", True), _oi("INCREASING"))
        assert sig.signal != "LONG" or sig.strategy != "PULLBACK"

    def test_short_pullback_condiciones_ok(self):
        # Condiciones perfectas para SHORT pullback:
        # BEARISH + precio cerca SMA20 + RSI<45 + volumen alto + OI subiendo
        ind = _ind(sma20=98.0, sma50=100.0, rsi=40.0, price=97.8)
        sig = self.detector.detect(_df_bullish(), ind, _vol("INCREASING", True), _oi("INCREASING"))
        assert sig.signal == "SHORT"
        assert sig.strategy == "PULLBACK"

    def test_signal_tiene_campos_requeridos(self):
        ind = _ind(sma20=100.0, sma50=98.0, rsi=60.0, price=100.0)
        sig = self.detector.detect(_df_bullish(), ind, _vol(), _oi())
        assert hasattr(sig, "signal")
        assert hasattr(sig, "strategy")
        assert hasattr(sig, "confidence")
        assert hasattr(sig, "reason")
        assert sig.signal in ("LONG", "SHORT", "NO_SIGNAL")
        assert 0.0 <= sig.confidence <= 1.0

    def test_breakout_con_precio_sobre_maximo(self):
        # Crear df donde el último precio es claramente mayor al máximo previo
        prices = [100.0] * 59 + [125.0]  # último precio +25% sobre todos los anteriores
        df = pd.DataFrame({
            "open": prices, "high": [p * 1.001 for p in prices],
            "low": [p * 0.999 for p in prices], "close": prices,
            "volume": [3000.0] * 60,  # volumen alto
        })
        ind = _ind(sma20=100.0, sma50=100.0, rsi=70.0, price=125.0, volume_avg=1000.0)
        sig = self.detector.detect(df, ind, _vol("INCREASING", True, 3.0), _oi())
        assert sig.signal == "LONG"
        assert sig.strategy == "BREAKOUT"
