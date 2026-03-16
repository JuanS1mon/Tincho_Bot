"""
analysis/trend_detector.py
==========================
Detecta la tendencia con SMA20 vs SMA50 y una zona neutral configurable.

Reglas:
    BULLISH: SMA20 > SMA50 con diferencia >= 0.1%
    BEARISH: SMA20 < SMA50 con diferencia <= -0.1%
    NEUTRAL: diferencia absoluta < 0.1%
"""
from __future__ import annotations

from enum import Enum

from tools.indicator_tool import Indicators


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class TrendDetector:
    """Determina la tendencia de mercado a partir de las tres medias móviles."""

    NEUTRAL_THRESHOLD_PCT = 0.1

    def detect(self, indicators: Indicators) -> Trend:
        sma20  = indicators.sma20
        sma50  = indicators.sma50

        if sma50 == 0:
            return Trend.NEUTRAL

        diff_pct = (sma20 - sma50) / sma50 * 100
        if abs(diff_pct) < self.NEUTRAL_THRESHOLD_PCT:
            return Trend.NEUTRAL
        if diff_pct > 0:
            return Trend.BULLISH
        return Trend.BEARISH

    def describe(self, indicators: Indicators) -> dict:
        """Retorna dict con tendencia y métricas asociadas."""
        trend = self.detect(indicators)
        sma50 = indicators.sma50
        return {
            "trend": trend.value,
            "sma20": indicators.sma20,
            "sma50": indicators.sma50,
            "sma100": indicators.sma100,
            "diff_pct": round(
                (indicators.sma20 - sma50) / sma50 * 100, 3
            ) if sma50 != 0 else 0,
            "sma20_vs_sma50_pct": round(
                (indicators.sma20 - sma50) / sma50 * 100, 3
            ) if sma50 != 0 else 0,
            "sma50_vs_sma100_pct": round(
                (sma50 - indicators.sma100) / indicators.sma100 * 100, 3
            ) if indicators.sma100 != 0 else 0,
        }


# Instancia global
trend_detector = TrendDetector()
