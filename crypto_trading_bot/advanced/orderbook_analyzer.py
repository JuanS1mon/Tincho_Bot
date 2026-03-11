"""
Advanced - Order Book Analyzer
================================
Analiza el order book para extraer señales de mercado:
  - Bid/ask spread
  - Profundidad acumulada
  - Imbalance ratio (presión compradora vs vendedora)
  - Muros de soporte/resistencia por concentración de órdenes
"""

from typing import Dict, List, Optional, Tuple

from config.logger import get_logger

logger = get_logger(__name__)


class OrderBookAnalyzer:
    """
    Analiza el order book para detectar señales de mercado.
    Usa polling REST cada 15 min (sin WebSocket).
    """

    def analyze(self, symbol: str, order_book: dict) -> dict:
        """
        Análisis completo del order book.
        
        Args:
            symbol: Par de trading.
            order_book: Dict con 'bids' y 'asks'.
            
        Returns:
            Dict con métricas del order book.
        """
        bids = order_book.get("bids", [])
        asks = order_book.get("asks", [])

        if not bids or not asks:
            logger.warning(f"Order book vacío para {symbol}")
            return self._empty_analysis(symbol)

        # --- Spread ---
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        spread = best_ask - best_bid
        spread_pct = (spread / best_bid * 100) if best_bid > 0 else 0

        # --- Profundidad acumulada ---
        bid_depth = sum(price * qty for price, qty in bids)
        ask_depth = sum(price * qty for price, qty in asks)

        # --- Imbalance Ratio ---
        # > 1.0 = más presión de compra, < 1.0 = más presión de venta
        total_depth = bid_depth + ask_depth
        imbalance_ratio = bid_depth / ask_depth if ask_depth > 0 else 1.0

        # Clasificar presión
        if imbalance_ratio > 1.3:
            buy_pressure = "strong"
        elif imbalance_ratio > 1.1:
            buy_pressure = "moderate"
        elif imbalance_ratio < 0.7:
            buy_pressure = "weak"  # Presión vendedora
        elif imbalance_ratio < 0.9:
            buy_pressure = "slightly_weak"
        else:
            buy_pressure = "neutral"

        # --- Muros de soporte/resistencia ---
        support_walls = self._detect_walls(bids, side="support")
        resistance_walls = self._detect_walls(asks, side="resistance")

        analysis = {
            "symbol": symbol,
            "best_bid": round(best_bid, 2),
            "best_ask": round(best_ask, 2),
            "spread": round(spread, 4),
            "spread_pct": round(spread_pct, 4),
            "bid_depth": round(bid_depth, 2),
            "ask_depth": round(ask_depth, 2),
            "imbalance_ratio": round(imbalance_ratio, 4),
            "buy_pressure": buy_pressure,
            "support_walls": support_walls,
            "resistance_walls": resistance_walls,
        }

        logger.debug(
            f"OrderBook {symbol}: spread={spread_pct:.4f}%, "
            f"imbalance={imbalance_ratio:.2f}, pressure={buy_pressure}"
        )

        return analysis

    def _detect_walls(
        self, orders: List[list], side: str, top_n: int = 3
    ) -> List[dict]:
        """
        Detecta muros de soporte o resistencia.
        Un "muro" es una concentración anormal de órdenes a un precio.
        
        Args:
            orders: Lista de [price, qty].
            side: "support" o "resistance".
            top_n: Cantidad de muros a retornar.
            
        Returns:
            Lista de muros con precio, cantidad y valor en USDT.
        """
        if not orders:
            return []

        # Calcular valor USDT de cada orden
        order_values = [
            {
                "price": round(price, 2),
                "quantity": round(qty, 6),
                "value_usdt": round(price * qty, 2),
            }
            for price, qty in orders
        ]

        # Calcular media y encontrar órdenes significativamente mayores
        values = [o["value_usdt"] for o in order_values]
        if not values:
            return []

        mean_value = sum(values) / len(values)

        # Filtrar órdenes > 2x la media (muros significativos)
        walls = [o for o in order_values if o["value_usdt"] > mean_value * 2]

        # Ordenar por valor y tomar top N
        walls.sort(key=lambda x: x["value_usdt"], reverse=True)
        return walls[:top_n]

    def _empty_analysis(self, symbol: str) -> dict:
        """Retorna un análisis vacío cuando no hay datos."""
        return {
            "symbol": symbol,
            "best_bid": 0,
            "best_ask": 0,
            "spread": 0,
            "spread_pct": 0,
            "bid_depth": 0,
            "ask_depth": 0,
            "imbalance_ratio": 1.0,
            "buy_pressure": "unknown",
            "support_walls": [],
            "resistance_walls": [],
        }
