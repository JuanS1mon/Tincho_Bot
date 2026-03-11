"""
analysis/signal_detector.py
============================
Detecta señales de trading según dos estrategias:

1. Trend + Pullback + Volumen (estrategia principal)
   LONG:  tendencia BULLISH + precio cerca SMA20 + RSI > 50 + volumen creciente + OI subiendo
   SHORT: tendencia BEARISH + precio cerca SMA20 + RSI < 45 + volumen alto + OI subiendo

2. Breakout
   precio > máximo últimas 20 velas + volumen > 1.5× promedio
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from tools.indicator_tool import Indicators
from analysis.trend_detector import Trend, trend_detector
from analysis.volume_analyzer import VolumeAnalysis
from analysis.open_interest_analyzer import OIAnalysis


@dataclass
class TradingSignal:
    signal: str            # LONG | SHORT | NO_SIGNAL
    strategy: str          # PULLBACK | BREAKOUT | NONE
    confidence: float      # 0.0 – 1.0 estimada localmente
    reason: str            # descripción de los criterios cumplidos


class SignalDetector:
    """Detecta señales de entrada aplicando las dos estrategias."""

    # Pullback: precio debe estar dentro de X% de SMA20
    SMA20_PROXIMITY_PCT: float = 0.015  # 1.5%

    def detect(
        self,
        df: pd.DataFrame,
        indicators: Indicators,
        volume_analysis: VolumeAnalysis,
        oi_analysis: OIAnalysis,
    ) -> TradingSignal:
        """Evalúa ambas estrategias y retorna la señal de mayor prioridad."""

        # 1. Intentar señal pullback
        pullback = self._pullback_signal(indicators, volume_analysis, oi_analysis)
        if pullback.signal != "NO_SIGNAL":
            return pullback

        # 2. Intentar señal breakout
        breakout = self._breakout_signal(df, indicators, volume_analysis)
        return breakout

    # ── Estrategia 1: Pullback ─────────────────────────────────────────────

    def _pullback_signal(
        self,
        ind: Indicators,
        vol: VolumeAnalysis,
        oi: OIAnalysis,
    ) -> TradingSignal:
        trend = trend_detector.detect(ind)
        proximity = abs(ind.price - ind.sma20) / ind.sma20 if ind.sma20 > 0 else 1

        oi_rising = oi.trend == "INCREASING"
        vol_ok = vol.trend == "INCREASING" or vol.is_high_volume

        # ── LONG ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BULLISH
            and proximity <= self.SMA20_PROXIMITY_PCT
            and ind.rsi > 50
            and vol_ok
            and oi_rising
        ):
            score = self._count_conditions(
                trend == Trend.BULLISH,
                proximity <= self.SMA20_PROXIMITY_PCT,
                ind.rsi > 55,
                vol.is_high_volume,
                oi_rising,
            )
            return TradingSignal(
                signal="LONG",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BULLISH | precio {proximity*100:.2f}% de SMA20 | "
                    f"RSI={ind.rsi:.1f} | Volumen {vol.trend} | OI {oi.trend}"
                ),
            )

        # ── SHORT ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BEARISH
            and proximity <= self.SMA20_PROXIMITY_PCT
            and ind.rsi < 45
            and vol_ok
            and oi_rising
        ):
            score = self._count_conditions(
                trend == Trend.BEARISH,
                proximity <= self.SMA20_PROXIMITY_PCT,
                ind.rsi < 40,
                vol.is_high_volume,
                oi_rising,
            )
            return TradingSignal(
                signal="SHORT",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BEARISH | precio {proximity*100:.2f}% de SMA20 | "
                    f"RSI={ind.rsi:.1f} | Volumen {vol.trend} | OI {oi.trend}"
                ),
            )

        return TradingSignal("NO_SIGNAL", "NONE", 0.0, "Sin condiciones de pullback cumplidas")

    # ── Estrategia 2: Breakout ─────────────────────────────────────────────

    def _breakout_signal(
        self,
        df: pd.DataFrame,
        ind: Indicators,
        vol: VolumeAnalysis,
    ) -> TradingSignal:
        if len(df) < 20:
            return TradingSignal("NO_SIGNAL", "NONE", 0.0, "Datos insuficientes para breakout")

        high_20 = float(df["high"].iloc[-21:-1].max())
        price_breaks_out = ind.price > high_20
        volume_confirms = vol.volume_ratio >= 1.5

        if price_breaks_out and volume_confirms:
            return TradingSignal(
                signal="LONG",
                strategy="BREAKOUT",
                confidence=0.65,
                reason=(
                    f"Ruptura de máximo ({high_20:.2f}) | "
                    f"Volumen ratio={vol.volume_ratio:.2f}×"
                ),
            )

        return TradingSignal("NO_SIGNAL", "NONE", 0.0, "Sin breakout confirmado")

    @staticmethod
    def _count_conditions(*conditions: bool) -> int:
        return sum(1 for c in conditions if c)


# Instancia global
signal_detector = SignalDetector()
