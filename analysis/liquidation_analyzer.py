"""
analysis/liquidation_analyzer.py
==================================
Analiza liquidaciones forzadas para detectar:
  - Zonas donde se liquidan LONGS (caídas bruscas posibles)
  - Zonas donde se liquidan SHORTS (subidas bruscas posibles)
  - Niveles de precio con alta concentración de liquidaciones
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from agent.parameters_manager import parameters_manager


@dataclass
class LiquidationAnalysis:
    total_long_liquidations: float     # valor total liquidado en LONGS
    total_short_liquidations: float    # valor total liquidado en SHORTS
    avg_long_price: float              # precio promedio de liquidación LONG
    avg_short_price: float             # precio promedio de liquidación SHORT
    dominant_side: str                 # LONG_DOMINANT | SHORT_DOMINANT | BALANCED
    signal: str                        # CASCADE_DOWN | CASCADE_UP | NEUTRAL
    description: str


class LiquidationAnalyzer:
    """Detecta presión de liquidaciones y posibles movimientos rápidos."""

    def analyze(self, liquidations: List[dict]) -> LiquidationAnalysis:
        """
        liquidations: lista de dicts con keys:
          side (BUY=long liq, SELL=short liq), price, qty
        """
        if not liquidations:
            return LiquidationAnalysis(0, 0, 0, 0, "BALANCED", "NEUTRAL", "Sin datos de liquidaciones")

        long_liqs = [l for l in liquidations if l.get("side") == "BUY"]
        short_liqs = [l for l in liquidations if l.get("side") == "SELL"]

        # Valor total (precio * cantidad)
        total_long = sum(l["price"] * l["qty"] for l in long_liqs)
        total_short = sum(l["price"] * l["qty"] for l in short_liqs)

        # Precio promedio ponderado de liquidaciones
        avg_long_price = (
            sum(l["price"] * l["qty"] for l in long_liqs) / sum(l["qty"] for l in long_liqs)
            if long_liqs else 0
        )
        avg_short_price = (
            sum(l["price"] * l["qty"] for l in short_liqs) / sum(l["qty"] for l in short_liqs)
            if short_liqs else 0
        )

        # Lado dominante (ratio configurable por la IA)
        ratio = parameters_manager.params.liquidation_dominance_ratio
        if total_long > total_short * ratio:
            dominant = "LONG_DOMINANT"
            signal = "CASCADE_DOWN"
            desc = f"Longs liquidados ({ratio:.1f}x) → posible presión bajista adicional"
        elif total_short > total_long * ratio:
            dominant = "SHORT_DOMINANT"
            signal = "CASCADE_UP"
            desc = f"Shorts liquidados ({ratio:.1f}x) → posible short squeeze / subida brusca"
        else:
            dominant = "BALANCED"
            signal = "NEUTRAL"
            desc = "Liquidaciones equilibradas, sin señal clara"

        return LiquidationAnalysis(
            total_long_liquidations=round(total_long, 2),
            total_short_liquidations=round(total_short, 2),
            avg_long_price=round(avg_long_price, 2),
            avg_short_price=round(avg_short_price, 2),
            dominant_side=dominant,
            signal=signal,
            description=desc,
        )


# Instancia global
liquidation_analyzer = LiquidationAnalyzer()
