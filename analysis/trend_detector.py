"""
analysis/trend_detector.py
==========================
Detecta la tendencia del mercado comparando SMA20 vs SMA50.

Reglas:
  SMA20 > SMA50 → BULLISH
  SMA20 < SMA50 → BEARISH
  |SMA20 - SMA50| muy pequeño → NEUTRAL
"""
from __future__ import annotations

from enum import Enum

from tools.indicator_tool import Indicators


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TrendDetector:
    """Determina la tendencia de mercado a partir de los indicadores."""

    # Si la diferencia relativa entre SMA20 y SMA50 es menor a este umbral → NEUTRAL
    NEUTRAL_THRESHOLD: float = 0.001  # 0.1%

    def detect(self, indicators: Indicators) -> Trend:
        """
        Retorna la tendencia basándose en el cruce de medias móviles.
        """
        sma20, sma50 = indicators.sma20, indicators.sma50
        diff_pct = abs(sma20 - sma50) / sma50 if sma50 != 0 else 0

        if diff_pct < self.NEUTRAL_THRESHOLD:
            return Trend.NEUTRAL

        if sma20 > sma50:
            return Trend.BULLISH

        return Trend.BEARISH

    def describe(self, indicators: Indicators) -> dict:
        """Retorna dict con tendencia y métricas asociadas."""
        trend = self.detect(indicators)
        return {
            "trend": trend.value,
            "sma20": indicators.sma20,
            "sma50": indicators.sma50,
            "diff_pct": round(
                (indicators.sma20 - indicators.sma50) / indicators.sma50 * 100, 3
            ) if indicators.sma50 != 0 else 0,
        }


# Instancia global
trend_detector = TrendDetector()
