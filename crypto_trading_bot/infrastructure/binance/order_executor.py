"""
Infrastructure - Order Executor
=================================
Ejecuta órdenes de trading en Binance.
  - Modo paper: simula órdenes en memoria y las registra en DB.
  - Modo live: ejecuta contra la API real de Binance.
Soporta market orders y limit orders.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from config.logger import get_logger
from config.settings import settings
from domain.services.capital_allocator import TradeOrder

logger = get_logger(__name__)


class PaperTrade:
    """Representa un trade simulado en modo paper."""

    def __init__(self, order: TradeOrder):
        self.id = str(uuid.uuid4())[:8]
        self.symbol = order.symbol
        self.side = order.side
        self.amount_usdt = order.amount_usdt
        self.quantity = order.quantity
        self.price = order.price
        self.stop_loss = order.stop_loss
        self.take_profit = order.take_profit
        self.timestamp = datetime.utcnow()
        self.status = "FILLED"  # En paper siempre se ejecuta

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "amount_usdt": self.amount_usdt,
            "quantity": self.quantity,
            "price": self.price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "timestamp": self.timestamp.isoformat(),
            "status": self.status,
        }


class OrderExecutor:
    """
    Ejecutor de órdenes con soporte paper/live.
    
    En modo paper: simula la ejecución y mantiene historial en memoria.
    En modo live: ejecuta contra Binance API real.
    """

    def __init__(self, binance_client=None):
        """
        Args:
            binance_client: Instancia de BinanceClientWrapper (requerido para live).
        """
        self.binance_client = binance_client
        self.paper_trades: List[PaperTrade] = []
        self.paper_balance: Dict[str, float] = {"USDT": settings.INITIAL_CAPITAL}

    def execute_orders(self, orders: List[TradeOrder]) -> List[dict]:
        """
        Ejecuta una lista de órdenes.
        
        Args:
            orders: Lista de TradeOrder generadas por CapitalAllocator.
            
        Returns:
            Lista de resultados de ejecución.
        """
        results = []
        for order in orders:
            if settings.is_paper_mode:
                result = self._execute_paper(order)
            else:
                result = self._execute_live(order)
            results.append(result)
        return results

    def _execute_paper(self, order: TradeOrder) -> dict:
        """
        Simula la ejecución de una orden en modo paper.
        Actualiza balances ficticios en memoria.
        """
        paper_trade = PaperTrade(order)

        # Actualizar balance paper
        asset = order.symbol.replace("USDT", "")

        if order.side == "BUY":
            # Verificar que hay suficiente USDT
            if self.paper_balance.get("USDT", 0) >= order.amount_usdt:
                self.paper_balance["USDT"] = self.paper_balance.get("USDT", 0) - order.amount_usdt
                self.paper_balance[asset] = self.paper_balance.get(asset, 0) + order.quantity
                paper_trade.status = "FILLED"
            else:
                paper_trade.status = "REJECTED"
                logger.warning(
                    f"📄 PAPER: Orden rechazada - USDT insuficiente "
                    f"({self.paper_balance.get('USDT', 0):.2f} < {order.amount_usdt:.2f})"
                )
        elif order.side == "SELL":
            if self.paper_balance.get(asset, 0) >= order.quantity:
                self.paper_balance[asset] = self.paper_balance.get(asset, 0) - order.quantity
                self.paper_balance["USDT"] = self.paper_balance.get("USDT", 0) + order.amount_usdt
                paper_trade.status = "FILLED"
            else:
                paper_trade.status = "REJECTED"
                logger.warning(
                    f"📄 PAPER: Orden rechazada - {asset} insuficiente"
                )

        self.paper_trades.append(paper_trade)

        status_emoji = "✅" if paper_trade.status == "FILLED" else "❌"
        logger.info(
            f"📄 PAPER {status_emoji}: {order.side} {order.symbol} "
            f"{order.amount_usdt:.2f} USDT (qty={order.quantity:.6f} @ {order.price:.2f})"
        )

        return paper_trade.to_dict()

    def _execute_live(self, order: TradeOrder) -> dict:
        """
        Ejecuta una orden real en Binance.
        Soporta market orders y limit orders.
        """
        if not self.binance_client or not self.binance_client.client:
            logger.error("❌ LIVE: No hay conexión con Binance")
            return {"status": "ERROR", "reason": "No Binance connection"}

        try:
            client = self.binance_client.client

            if order.side == "BUY":
                result = client.order_market_buy(
                    symbol=order.symbol,
                    quoteOrderQty=order.amount_usdt,  # Compra por monto en USDT
                )
            else:
                result = client.order_market_sell(
                    symbol=order.symbol,
                    quantity=self._format_quantity(order.symbol, order.quantity),
                )

            logger.info(
                f"🔴 LIVE ✅: {order.side} {order.symbol} "
                f"{order.amount_usdt:.2f} USDT - OrderID: {result.get('orderId')}"
            )

            return {
                "status": "FILLED",
                "order_id": result.get("orderId"),
                "symbol": order.symbol,
                "side": order.side,
                "price": float(result.get("fills", [{}])[0].get("price", order.price)),
                "quantity": float(result.get("executedQty", 0)),
                "amount_usdt": order.amount_usdt,
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as e:
            logger.error(f"🔴 LIVE ❌: Error ejecutando orden {order.symbol}: {e}")
            return {
                "status": "ERROR",
                "symbol": order.symbol,
                "side": order.side,
                "reason": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def execute_limit_order(
        self, symbol: str, side: str, quantity: float, price: float
    ) -> dict:
        """
        Ejecuta una orden limit (solo modo live).
        
        Args:
            symbol: Par de trading.
            side: "BUY" o "SELL".
            quantity: Cantidad del activo.
            price: Precio límite.
        """
        if settings.is_paper_mode:
            logger.info(f"📄 PAPER: Limit order simulada {side} {symbol} @ {price}")
            return {
                "status": "FILLED",
                "type": "LIMIT",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
            }

        if not self.binance_client or not self.binance_client.client:
            return {"status": "ERROR", "reason": "No Binance connection"}

        try:
            client = self.binance_client.client
            result = client.create_order(
                symbol=symbol,
                side=side,
                type="LIMIT",
                timeInForce="GTC",
                quantity=self._format_quantity(symbol, quantity),
                price=str(price),
            )
            logger.info(f"🔴 LIVE: Limit order creada {side} {symbol} @ {price}")
            return {
                "status": result.get("status", "NEW"),
                "order_id": result.get("orderId"),
                "type": "LIMIT",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": price,
            }
        except Exception as e:
            logger.error(f"Error en limit order: {e}")
            return {"status": "ERROR", "reason": str(e)}

    def _format_quantity(self, symbol: str, quantity: float) -> str:
        """Formatea la cantidad según los requisitos del símbolo."""
        # Decimales según el activo
        if "BTC" in symbol:
            return f"{quantity:.5f}"
        elif "ETH" in symbol:
            return f"{quantity:.4f}"
        return f"{quantity:.6f}"

    def get_paper_balance(self) -> Dict[str, float]:
        """Retorna el balance simulado actual."""
        return self.paper_balance.copy()

    def get_paper_trades_history(self) -> List[dict]:
        """Retorna el historial de trades simulados."""
        return [t.to_dict() for t in self.paper_trades]
