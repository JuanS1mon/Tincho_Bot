"""
analysis/open_interest_analyzer.py
====================================
Analiza la tendencia del Open Interest para detectar
entrada de dinero institucional y confirmación de tendencia.

Combinación de señales:
  OI sube + precio sube → tendencia FUERTE/ALCISTA
  OI sube + precio baja → tendencia FUERTE/BAJISTA (presión bajista)
  OI baja + precio sube → rally sin convicción
  OI baja + precio baja → capitulación / cierre de posiciones
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class OIAnalysis:
    current_oi: float
    oi_change_pct: float         # cambio % respecto al inicio del historial
    trend: str                   # INCREASING | DECREASING | STABLE
    signal: str                  # STRONG_BULL | STRONG_BEAR | WEAK_RALLY | CAPITULATION | NEUTRAL
    description: str


class OpenInterestAnalyzer:
    """Interpreta la tendencia del open interest."""

    # Umbral mínimo para considerar movimiento significativo
    MIN_CHANGE_PCT: float = 0.5  # 0.5%

    def analyze(self, oi_history: List[dict], current_price: float, prev_price: float) -> OIAnalysis:
        """
        oi_history: lista de dicts con 'open_interest'
        current_price, prev_price: precios de cierre para correlacionar
        """
        if not oi_history or len(oi_history) < 2:
            return OIAnalysis(0, 0, "STABLE", "NEUTRAL", "Sin datos suficientes de OI")

        oi_values = [r["open_interest"] for r in oi_history]
        current_oi = oi_values[-1]
        prev_oi = oi_values[0]

        change_pct = ((current_oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0

        # Tendencia OI
        if change_pct > self.MIN_CHANGE_PCT:
            oi_trend = "INCREASING"
        elif change_pct < -self.MIN_CHANGE_PCT:
            oi_trend = "DECREASING"
        else:
            oi_trend = "STABLE"

        # Correlación OI + precio
        price_rising = current_price > prev_price

        if oi_trend == "INCREASING" and price_rising:
            signal = "STRONG_BULL"
            desc = "OI ↑ + precio ↑ → Tendencia alcista fuerte (institucional entrando LONG)"
        elif oi_trend == "INCREASING" and not price_rising:
            signal = "STRONG_BEAR"
            desc = "OI ↑ + precio ↓ → Tendencia bajista fuerte (institucional entrando SHORT)"
        elif oi_trend == "DECREASING" and price_rising:
            signal = "WEAK_RALLY"
            desc = "OI ↓ + precio ↑ → Rally sin convicción (short squeeze posible)"
        elif oi_trend == "DECREASING" and not price_rising:
            signal = "CAPITULATION"
            desc = "OI ↓ + precio ↓ → Capitulación / cierre masivo de posiciones"
        else:
            signal = "NEUTRAL"
            desc = "Open Interest estable, sin señal clara"

        return OIAnalysis(
            current_oi=round(current_oi, 2),
            oi_change_pct=round(change_pct, 3),
            trend=oi_trend,
            signal=signal,
            description=desc,
        )


# Instancia global
open_interest_analyzer = OpenInterestAnalyzer()
