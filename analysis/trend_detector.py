"""
analysis/trend_detector.py
==========================
Detecta la tendencia del mercado combinando SMA20, SMA50 y SMA100.

Reglas:
  BULLISH: SMA20 > SMA50 > SMA100 — las tres medias alineadas hacia arriba.
           Confirma tendencia alcista real (no rebotes dentro de una caída).
  BEARISH: SMA20 < SMA50             — la media corta ya giró a la baja.
           No exige SMA100 alineada: si el precio cae con fuerza, el SHORT
           se habilita en cuanto SMA20 cruza SMA50, sin esperar que SMA100
           también se alinee (lo que tardaría decenas de velas más).
  NEUTRAL: cualquier otra combinación (ej. SMA20 > SMA50 pero SMA50 < SMA100,
           típico de un rebote en una bajada mayor).
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

    def detect(self, indicators: Indicators) -> Trend:
        sma20  = indicators.sma20
        sma50  = indicators.sma50
        sma100 = indicators.sma100

        # LONG solo si las tres medias están ordenadas alcistas (filtro estricto)
        if sma20 > sma50 > sma100:
            return Trend.BULLISH

        # SHORT en cuanto SMA20 cruza SMA50 hacia abajo (reacción rápida)
        if sma20 < sma50:
            return Trend.BEARISH

        # SMA20 entre SMA50 y SMA100 → mercado sin dirección clara
        return Trend.NEUTRAL

    def describe(self, indicators: Indicators) -> dict:
        """Retorna dict con tendencia y métricas asociadas."""
        trend = self.detect(indicators)
        sma50 = indicators.sma50
        return {
            "trend": trend.value,
            "sma20": indicators.sma20,
            "sma50": indicators.sma50,
            "sma100": indicators.sma100,
            "sma20_vs_sma50_pct": round(
                (indicators.sma20 - sma50) / sma50 * 100, 3
            ) if sma50 != 0 else 0,
            "sma50_vs_sma100_pct": round(
                (sma50 - indicators.sma100) / indicators.sma100 * 100, 3
            ) if indicators.sma100 != 0 else 0,
        }


# Instancia global
trend_detector = TrendDetector()
