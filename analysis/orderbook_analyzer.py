"""
analysis/orderbook_analyzer.py
===============================
Analiza la profundidad del order book para detectar:
  - Muros de compra (grandes acumulaciones de bids)
  - Muros de venta (grandes acumulaciones de asks)
  - Soportes y resistencias reales del mercado
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class OrderBookAnalysis:
    buy_walls: List[Tuple[float, float]]   # [(price, qty), ...]
    sell_walls: List[Tuple[float, float]]  # [(price, qty), ...]
    best_bid: float
    best_ask: float
    spread: float
    spread_pct: float
    buy_pressure: float   # % del volumen total en bids
    sell_pressure: float  # % del volumen total en asks
    imbalance: str        # BUY_DOMINANT | SELL_DOMINANT | BALANCED


class OrderBookAnalyzer:
    """Detecta muros y desequilibrios en el order book."""

    # Una orden es "muro" si su tamaño ≥ WALL_MULTIPLIER * promedio
    WALL_MULTIPLIER: float = 3.0

    def analyze(self, orderbook: dict) -> OrderBookAnalysis:
        """
        orderbook: dict con keys 'bids' y 'asks'
        Cada lista: [[price, quantity], ...]
        """
        bids: List[List[float]] = orderbook.get("bids", [])
        asks: List[List[float]] = orderbook.get("asks", [])

        if not bids or not asks:
            return self._empty_analysis()

        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        spread_pct = (spread / best_ask * 100) if best_ask > 0 else 0

        # Calcular volumen total de cada lado
        total_bid_vol = sum(b[1] for b in bids)
        total_ask_vol = sum(a[1] for a in asks)
        total_vol = total_bid_vol + total_ask_vol

        buy_pressure = (total_bid_vol / total_vol * 100) if total_vol > 0 else 50
        sell_pressure = 100 - buy_pressure

        # Detectar muros
        buy_walls = self._detect_walls(bids)
        sell_walls = self._detect_walls(asks)

        # Imbalance
        if buy_pressure > 60:
            imbalance = "BUY_DOMINANT"
        elif sell_pressure > 60:
            imbalance = "SELL_DOMINANT"
        else:
            imbalance = "BALANCED"

        return OrderBookAnalysis(
            buy_walls=buy_walls,
            sell_walls=sell_walls,
            best_bid=round(best_bid, 4),
            best_ask=round(best_ask, 4),
            spread=round(spread, 4),
            spread_pct=round(spread_pct, 4),
            buy_pressure=round(buy_pressure, 2),
            sell_pressure=round(sell_pressure, 2),
            imbalance=imbalance,
        )

    def _detect_walls(self, levels: List[List[float]]) -> List[Tuple[float, float]]:
        """Identifica niveles con cantidad significativamente mayor al promedio."""
        if not levels:
            return []
        quantities = [lvl[1] for lvl in levels]
        avg_qty = sum(quantities) / len(quantities)
        threshold = avg_qty * self.WALL_MULTIPLIER
        return [
            (round(lvl[0], 4), round(lvl[1], 2))
            for lvl in levels
            if lvl[1] >= threshold
        ]

    @staticmethod
    def _empty_analysis() -> OrderBookAnalysis:
        return OrderBookAnalysis(
            buy_walls=[], sell_walls=[],
            best_bid=0, best_ask=0,
            spread=0, spread_pct=0,
            buy_pressure=50, sell_pressure=50,
            imbalance="BALANCED",
        )


# Instancia global
orderbook_analyzer = OrderBookAnalyzer()
