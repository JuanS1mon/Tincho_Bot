"""
Advanced - Whale Detector
===========================
Detecta actividad de ballenas (grandes órdenes) en el order book y trades recientes.
Umbrales configurables desde .env:
  - WHALE_THRESHOLD_BTC / WHALE_THRESHOLD_ETH (por cantidad fija)
  - WHALE_STD_MULTIPLIER (por desviación estándar del promedio)
"""

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class WhaleAlert:
    """Representa una alerta de actividad de ballena."""

    def __init__(
        self,
        symbol: str,
        alert_type: str,
        side: str,
        quantity: float,
        price: float,
    ):
        self.symbol = symbol
        self.alert_type = alert_type  # "order_book" o "trade"
        self.side = side  # "bid" o "ask" o "buy" o "sell"
        self.quantity = quantity
        self.price = price
        self.total_value_usdt = quantity * price
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "type": self.alert_type,
            "side": self.side,
            "quantity": round(self.quantity, 6),
            "price": round(self.price, 2),
            "total_value_usdt": round(self.total_value_usdt, 2),
            "timestamp": self.timestamp.isoformat(),
        }


class WhaleDetector:
    """
    Detecta actividad de ballenas en el mercado.
    
    Analiza:
    1. Order book: busca órdenes con volumen anormalmente alto.
    2. Trades recientes: detecta movimientos grandes.
    
    Umbrales configurables desde .env.
    """

    def __init__(self):
        self.thresholds = settings.whale_thresholds
        self.std_multiplier = settings.WHALE_STD_MULTIPLIER

    def detect_from_order_book(
        self, symbol: str, order_book: dict
    ) -> List[WhaleAlert]:
        """
        Detecta ballenas en el order book.
        
        Args:
            symbol: Par de trading.
            order_book: Dict con 'bids' y 'asks' ([[price, qty], ...]).
            
        Returns:
            Lista de WhaleAlert detectadas.
        """
        alerts = []
        threshold = self.thresholds.get(symbol, 5.0)

        # Analizar bids (órdenes de compra grandes)
        bids = order_book.get("bids", [])
        if bids:
            bid_quantities = [qty for _, qty in bids]
            alerts.extend(
                self._detect_large_orders(
                    symbol, "bid", bids, bid_quantities, threshold
                )
            )

        # Analizar asks (órdenes de venta grandes)
        asks = order_book.get("asks", [])
        if asks:
            ask_quantities = [qty for _, qty in asks]
            alerts.extend(
                self._detect_large_orders(
                    symbol, "ask", asks, ask_quantities, threshold
                )
            )

        if alerts:
            logger.warning(
                f"🐋 {len(alerts)} alertas de ballena detectadas en {symbol} (order book)"
            )

        return alerts

    def detect_from_trades(
        self, symbol: str, trades: List[dict]
    ) -> List[WhaleAlert]:
        """
        Detecta ballenas en los trades recientes.
        
        Args:
            symbol: Par de trading.
            trades: Lista de trades recientes con 'price', 'quantity', 'is_buyer_maker'.
            
        Returns:
            Lista de WhaleAlert detectadas.
        """
        if not trades:
            return []

        alerts = []
        threshold = self.thresholds.get(symbol, 5.0)

        # Calcular estadísticas de los trades
        quantities = [t["quantity"] for t in trades]
        if not quantities:
            return []

        mean_qty = np.mean(quantities)
        std_qty = np.std(quantities)
        dynamic_threshold = mean_qty + (self.std_multiplier * std_qty)

        for trade in trades:
            qty = trade["quantity"]
            price = trade["price"]

            # Detectar por umbral fijo O por desviación estándar
            if qty >= threshold or qty >= dynamic_threshold:
                side = "sell" if trade.get("is_buyer_maker", False) else "buy"
                alert = WhaleAlert(
                    symbol=symbol,
                    alert_type="trade",
                    side=side,
                    quantity=qty,
                    price=price,
                )
                alerts.append(alert)

        if alerts:
            logger.warning(
                f"🐋 {len(alerts)} ballenas detectadas en {symbol} (trades recientes)"
            )

        return alerts

    def _detect_large_orders(
        self,
        symbol: str,
        side: str,
        orders: List[list],
        quantities: List[float],
        fixed_threshold: float,
    ) -> List[WhaleAlert]:
        """Detecta órdenes grandes por umbral fijo y dinámico."""
        alerts = []

        if not quantities:
            return alerts

        mean_qty = np.mean(quantities)
        std_qty = np.std(quantities)
        dynamic_threshold = mean_qty + (self.std_multiplier * std_qty)

        for price, qty in orders:
            if qty >= fixed_threshold or qty >= dynamic_threshold:
                alert = WhaleAlert(
                    symbol=symbol,
                    alert_type="order_book",
                    side=side,
                    quantity=qty,
                    price=price,
                )
                alerts.append(alert)

        return alerts

    def analyze(
        self, symbol: str, order_book: dict, trades: List[dict]
    ) -> Dict:
        """
        Análisis completo de actividad de ballenas.
        
        Returns:
            Dict con alertas y resumen.
        """
        ob_alerts = self.detect_from_order_book(symbol, order_book)
        trade_alerts = self.detect_from_trades(symbol, trades)
        all_alerts = ob_alerts + trade_alerts

        return {
            "symbol": symbol,
            "total_alerts": len(all_alerts),
            "order_book_alerts": len(ob_alerts),
            "trade_alerts": len(trade_alerts),
            "alerts": [a.to_dict() for a in all_alerts],
            "whale_activity_detected": len(all_alerts) > 0,
        }
