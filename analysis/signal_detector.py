"""
analysis/signal_detector.py
============================
Detecta señales de trading según dos estrategias:

1. Trend + Pullback + Volumen (estrategia principal)
    LONG:  tendencia BULLISH + precio cerca SMA20 + RSI > 50 + volumen creciente + OI subiendo
    SHORT: tendencia BEARISH + precio cerca SMA20 + RSI < umbral dinámico + volumen alto + OI subiendo

2. Breakout (alcista y bajista)
    LONG:  precio > máximo últimas 20 velas + volumen > 1.5× promedio
    SHORT: precio < mínimo últimas 20 velas + volumen > 1.5× promedio
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
        rsi_momentum: float = 0.0,
    ) -> TradingSignal:
        """Evalúa ambas estrategias y retorna la señal de mayor prioridad."""

        # 1. Intentar señal pullback
        pullback = self._pullback_signal(indicators, volume_analysis, oi_analysis, rsi_momentum)
        if pullback.signal != "NO_SIGNAL":
            return pullback

        # 2. Intentar señal breakout
        breakout = self._breakout_signal(df, indicators, volume_analysis)
        # Si tampoco hubo breakout, conservar razón detallada del pullback
        # para facilitar diagnóstico de filtros en logs.
        if breakout.signal == "NO_SIGNAL":
            return pullback
        return breakout

    # ── Estrategia 1: Pullback ─────────────────────────────────────────────

    def _pullback_signal(
        self,
        ind: Indicators,
        vol: VolumeAnalysis,
        oi: OIAnalysis,
        rsi_momentum: float = 0.0,
    ) -> TradingSignal:
        p = parameters_manager.params
        trend = trend_detector.detect(ind)
        proximity = abs(ind.price - ind.sma20) / ind.sma20 if ind.sma20 > 0 else 1
        long_side_ok = ind.price >= ind.sma20 * (0.999 if p.tryhard_mode else 1.0)
        short_side_ok = ind.price <= ind.sma20 * (1.001 if p.tryhard_mode else 1.0)

        vol_ok = vol.trend == "INCREASING" or vol.is_high_volume
        long_oi_ok = oi.trend == "INCREASING" or oi.signal in ("STRONG_BULL", "WEAK_RALLY", "CAPITULATION")
        short_oi_ok = oi.trend == "INCREASING" or oi.signal in ("STRONG_BEAR", "CAPITULATION")

        # ── TRYHARD: relaja filtros de volumen, proximidad y OI ───────────────
        if p.tryhard_mode:
            vol_ok = vol.volume_ratio >= 0.15         # acepta volumen bajo — solo filtra ausencia total
            proximity_ok = True                        # sin restricción de distancia
            long_oi_ok = oi.trend in ("INCREASING", "STABLE") or oi.signal in ("STRONG_BULL", "WEAK_RALLY", "CAPITULATION")
            short_oi_ok = oi.trend in ("INCREASING", "STABLE") or oi.signal in ("STRONG_BEAR", "CAPITULATION")
        else:
            # Modo normal: limitamos pullback a una zona más estricta para reducir falsas entradas.
            # Aunque el parámetro dinámico sea más laxo, aplicamos un techo conservador de 1.5%.
            max_proximity = min(p.sma20_proximity_pct, 0.015)
            proximity_ok = proximity < max_proximity
            # En modo normal, aceptar volumen subpromedio moderado para no perder entradas
            # cuando el mercado está lateral pero con dirección clara.
            vol_ok = vol_ok or vol.volume_ratio >= 0.80

        # ── Ajuste dinámico del umbral RSI por momentum ───────────────────────
        # Ajuste simétrico: momentum alcista favorece LONG, momentum bajista favorece SHORT.
        # Filtro conservador: LONG solo si RSI supera al menos 50.
        effective_long_threshold = max(p.rsi_long_threshold, 50.0)
        effective_short_threshold = p.rsi_short_threshold
        momentum_str = ""
        if rsi_momentum >= 5.0 and ind.rsi <= p.rsi_overbought:
            reduction = min(rsi_momentum * 0.4, p.rsi_momentum_boost)
            effective_long_threshold = max(35.0, p.rsi_long_threshold - reduction)
            momentum_str = f" [RSI↑ momentum=+{rsi_momentum:.1f} → umbral={effective_long_threshold:.1f}]"
        elif rsi_momentum <= -5.0:
            # RSI cayendo → más conservador para LONG
            increase = min(abs(rsi_momentum) * 0.3, p.rsi_momentum_boost / 2)
            effective_long_threshold = min(65.0, p.rsi_long_threshold + increase)
            # RSI cayendo → menos exigente para SHORT (permite capturar downside momentum)
            short_relax = min(abs(rsi_momentum) * 0.4, p.rsi_momentum_boost)
            effective_short_threshold = min(70.0, p.rsi_short_threshold + short_relax)
            momentum_str = (
                f" [RSI↓ momentum={rsi_momentum:.1f} → "
                f"long_umbral={effective_long_threshold:.1f} | short_umbral={effective_short_threshold:.1f}]"
            )

        # ── LONG ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BULLISH
            and proximity_ok
            and long_side_ok
            and ind.rsi > effective_long_threshold
            and vol_ok
            and long_oi_ok
        ):
            score = self._count_conditions(
                trend == Trend.BULLISH,
                proximity_ok,
                ind.rsi > effective_long_threshold + 5,
                vol.is_high_volume,
                long_oi_ok,
            )
            return TradingSignal(
                signal="LONG",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BULLISH | precio {proximity*100:.2f}% de SMA20 "
                    f"(max {'TRYHARD' if p.tryhard_mode else f'{p.sma20_proximity_pct*100:.1f}%'}) | "
                    f"RSI={ind.rsi:.1f}>{effective_long_threshold:.1f}{momentum_str} | "
                    f"Volumen {vol.trend} ({vol.volume_ratio:.2f}x) | OI {oi.trend}"
                ),
            )

        # ── SHORT ─────────────────────────────────────────────────────────────
        if (
            trend == Trend.BEARISH
            and proximity_ok
            and short_side_ok
            and ind.rsi < effective_short_threshold
            and vol_ok
            and short_oi_ok
        ):
            score = self._count_conditions(
                trend == Trend.BEARISH,
                proximity_ok,
                ind.rsi < effective_short_threshold - 5,
                vol.is_high_volume,
                short_oi_ok,
            )
            return TradingSignal(
                signal="SHORT",
                strategy="PULLBACK",
                confidence=round(score / 5, 2),
                reason=(
                    f"Tendencia BEARISH | precio {proximity*100:.2f}% de SMA20 "
                    f"(max {'TRYHARD' if p.tryhard_mode else f'{p.sma20_proximity_pct*100:.1f}%'}) | "
                    f"RSI={ind.rsi:.1f}<{effective_short_threshold:.1f}{momentum_str} | "
                    f"Volumen {vol.trend} ({vol.volume_ratio:.2f}x) | OI {oi.trend}"
                ),
            )

        # Construir razón detallada del NO_SIGNAL
        missing = []
        if not proximity_ok:
            missing.append(f"precio lejos de SMA20 ({proximity*100:.2f}% > {p.sma20_proximity_pct*100:.1f}%)")
        if trend == Trend.BULLISH and not long_side_ok:
            missing.append("precio por debajo de SMA20 para LONG")
        if trend == Trend.BEARISH and not short_side_ok:
            missing.append("precio por encima de SMA20 para SHORT")
        if trend == Trend.BULLISH and rsi_momentum <= -8.0 and ind.price < ind.sma20:
            missing.append("momentum bajista fuerte: LONG desaconsejado")
        if trend == Trend.BULLISH and ind.rsi <= effective_long_threshold:
            missing.append(f"RSI insuficiente ({ind.rsi:.1f} <= {effective_long_threshold:.1f}{momentum_str})")
        if trend == Trend.BEARISH and ind.rsi >= effective_short_threshold:
            missing.append(f"RSI insuficiente ({ind.rsi:.1f} >= {effective_short_threshold:.1f}{momentum_str})")
        if not vol_ok:
            missing.append("volumen bajo")
        if trend == Trend.BULLISH and not long_oi_ok:
            needed = "INCREASING/STABLE o señal STRONG_BULL/WEAK_RALLY/CAPITULATION" if p.tryhard_mode else "INCREASING o señal STRONG_BULL/WEAK_RALLY/CAPITULATION"
            missing.append(f"OI {oi.trend} ({oi.signal}) no confirma LONG (necesita {needed})")
        if trend == Trend.BEARISH and not short_oi_ok:
            needed = "INCREASING/STABLE o señal STRONG_BEAR/CAPITULATION" if p.tryhard_mode else "INCREASING o señal STRONG_BEAR/CAPITULATION"
            missing.append(f"OI {oi.trend} ({oi.signal}) no confirma SHORT (necesita {needed})")
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
        p = parameters_manager.params
        if len(df) < 20:
            return TradingSignal("NO_SIGNAL", "NONE", 0.0, "Datos insuficientes para breakout")

        high_20 = float(df["high"].iloc[-21:-1].max())
        low_20 = float(df["low"].iloc[-21:-1].min())
        price_breaks_out = ind.price > high_20
        price_breaks_down = ind.price < low_20
        # Umbral más flexible para capturar rupturas en BTC/ETH sin exigir picos extremos.
        volume_threshold = 1.10 if p.tryhard_mode else 1.20
        volume_confirms = vol.volume_ratio >= volume_threshold

        if price_breaks_out and volume_confirms:
            return TradingSignal(
                signal="LONG",
                strategy="BREAKOUT",
                confidence=0.65,
                reason=(
                    f"Ruptura de máximo ({high_20:.2f}) | "
                    f"Volumen ratio={vol.volume_ratio:.2f}× (min {volume_threshold:.2f}×)"
                ),
            )

        if price_breaks_down and volume_confirms:
            return TradingSignal(
                signal="SHORT",
                strategy="BREAKOUT",
                confidence=0.65,
                reason=(
                    f"Ruptura de mínimo ({low_20:.2f}) | "
                    f"Volumen ratio={vol.volume_ratio:.2f}× (min {volume_threshold:.2f}×)"
                ),
            )

        return TradingSignal("NO_SIGNAL", "NONE", 0.0, "Sin breakout confirmado")

    @staticmethod
    def _count_conditions(*conditions: bool) -> int:
        return sum(1 for c in conditions if c)


# Instancia global
signal_detector = SignalDetector()
