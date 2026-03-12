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
from agent.parameters_manager import parameters_manager


@dataclass
class TradingSignal:
    signal: str            # LONG | SHORT | NO_SIGNAL
    strategy: str          # PULLBACK | BREAKOUT | NONE
    confidence: float      # 0.0 – 1.0 estimada localmente
    reason: str            # descripción de los criterios cumplidos


class SignalDetector:
    """Detecta señales de entrada aplicando las dos estrategias."""

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
        p = parameters_manager.params
        trend = trend_detector.detect(ind)
        proximity = abs(ind.price - ind.sma20) / ind.sma20 if ind.sma20 > 0 else 1

        oi_rising = oi.trend == "INCREASING"
        vol_ok = vol.trend == "INCREASING" or vol.is_high_volume

        # ── LONG ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BULLISH
            and proximity <= p.sma20_proximity_pct
            and ind.rsi > p.rsi_long_threshold
            and vol_ok
            and oi_rising
        ):
            score = self._count_conditions(
                trend == Trend.BULLISH,
                proximity <= p.sma20_proximity_pct,
                ind.rsi > p.rsi_long_threshold + 5,
                vol.is_high_volume,
                oi_rising,
            )
            return TradingSignal(
                signal="LONG",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BULLISH | precio {proximity*100:.2f}% de SMA20 "
                    f"(max {p.sma20_proximity_pct*100:.1f}%) | "
                    f"RSI={ind.rsi:.1f}>{p.rsi_long_threshold} | "
                    f"Volumen {vol.trend} | OI {oi.trend}"
                ),
            )

        # ── SHORT ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BEARISH
            and proximity <= p.sma20_proximity_pct
            and ind.rsi < p.rsi_short_threshold
            and vol_ok
            and oi_rising
        ):
            score = self._count_conditions(
                trend == Trend.BEARISH,
                proximity <= p.sma20_proximity_pct,
                ind.rsi < p.rsi_short_threshold - 5,
                vol.is_high_volume,
                oi_rising,
            )
            return TradingSignal(
                signal="SHORT",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BEARISH | precio {proximity*100:.2f}% de SMA20 "
                    f"(max {p.sma20_proximity_pct*100:.1f}%) | "
                    f"RSI={ind.rsi:.1f}<{p.rsi_short_threshold} | "
                    f"Volumen {vol.trend} | OI {oi.trend}"
                ),
            )

        # Construir razón detallada del NO_SIGNAL
        missing = []
        if proximity > p.sma20_proximity_pct:
            missing.append(f"precio lejos de SMA20 ({proximity*100:.2f}% > {p.sma20_proximity_pct*100:.1f}%)")
        if trend == Trend.BULLISH and ind.rsi <= p.rsi_long_threshold:
            missing.append(f"RSI insuficiente ({ind.rsi:.1f} <= {p.rsi_long_threshold})")
        if trend == Trend.BEARISH and ind.rsi >= p.rsi_short_threshold:
            missing.append(f"RSI insuficiente ({ind.rsi:.1f} >= {p.rsi_short_threshold})")
        if not vol_ok:
            missing.append("volumen bajo")
        if not oi_rising:
            missing.append(f"OI {oi.trend} (necesita INCREASING)")
        if trend == Trend.NEUTRAL:
            missing.append("tendencia NEUTRAL (necesita BULLISH o BEARISH)")

        reason = " | ".join(missing) if missing else "Sin condiciones de pullback cumplidas"
        return TradingSignal("NO_SIGNAL", "NONE", 0.0, reason)

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
