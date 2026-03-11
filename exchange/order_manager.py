"""
binance/order_manager.py
=========================
Gestiona la ejecución de órdenes en Binance Futures:
  - Configurar apalancamiento
  - Abrir órdenes market (LONG / SHORT)
  - Colocar Stop Loss y Take Profit (precio fijo)
  - Activar trailing stop
  - Cerrar posición
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from binance.exceptions import BinanceAPIException

from exchange.futures_client import futures_client
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class OrderManager:
    """Interfaz de alto nivel para operar en Binance Futures."""

    def __init__(self) -> None:
        self._client = futures_client

    # ── Apalancamiento ────────────────────────────────────────────────────────

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Establece el apalancamiento para el símbolo indicado."""
        try:
            result = self._client.safe_call(
                self._client.client.futures_change_leverage,
                symbol=symbol,
                leverage=leverage,
            )
            logger.info("Leverage %s → %dx", symbol, leverage)
            return result
        except BinanceAPIException as exc:
            error_logger.error("set_leverage(%s, %d) error: %s", symbol, leverage, exc)
            raise

    # ── Órdenes market ────────────────────────────────────────────────────────

    def open_long(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """Abre posición LONG (compra) con orden market."""
        return self._place_market_order(symbol, "BUY", quantity)

    def open_short(self, symbol: str, quantity: float) -> Dict[str, Any]:
        """Abre posición SHORT (venta) con orden market."""
        return self._place_market_order(symbol, "SELL", quantity)

    def _place_market_order(
        self, symbol: str, side: str, quantity: float
    ) -> Dict[str, Any]:
        try:
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=quantity,
            )
            logger.info(
                "Orden market ejecutada: %s %s | qty=%s | orderId=%s",
                side, symbol, quantity, order.get("orderId"),
            )
            return order
        except BinanceAPIException as exc:
            error_logger.error("_place_market_order(%s %s) error: %s", side, symbol, exc)
            raise

    # ── Stop Loss / Take Profit ───────────────────────────────────────────────

    def set_stop_loss(
        self, symbol: str, side: str, stop_price: float, quantity: float
    ) -> Dict[str, Any]:
        """
        Coloca orden STOP_MARKET.
        side = 'BUY' para cerrar un SHORT, 'SELL' para cerrar un LONG.
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        try:
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="STOP_MARKET",
                stopPrice=round(stop_price, 2),
                quantity=quantity,
                reduceOnly="true",
            )
            logger.info("Stop Loss colocado: %s @ %.2f", symbol, stop_price)
            return order
        except BinanceAPIException as exc:
            error_logger.error("set_stop_loss(%s) error: %s", symbol, exc)
            raise

    def set_take_profit(
        self, symbol: str, side: str, tp_price: float, quantity: float
    ) -> Dict[str, Any]:
        """
        Coloca orden TAKE_PROFIT_MARKET.
        side = 'BUY' para cerrar un SHORT, 'SELL' para cerrar un LONG.
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        try:
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=round(tp_price, 2),
                quantity=quantity,
                reduceOnly="true",
            )
            logger.info("Take Profit colocado: %s @ %.2f", symbol, tp_price)
            return order
        except BinanceAPIException as exc:
            error_logger.error("set_take_profit(%s) error: %s", symbol, exc)
            raise

    def set_trailing_stop(
        self, symbol: str, side: str, callback_rate: float, quantity: float
    ) -> Dict[str, Any]:
        """
        Coloca trailing stop con `callbackRate` en %.
        callback_rate: porcentaje de trailing (ej. 1.0 para 1%)
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        try:
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="TRAILING_STOP_MARKET",
                callbackRate=round(callback_rate, 1),
                quantity=quantity,
                reduceOnly="true",
            )
            logger.info("Trailing Stop %s @ callback=%.1f%%", symbol, callback_rate)
            return order
        except BinanceAPIException as exc:
            error_logger.error("set_trailing_stop(%s) error: %s", symbol, exc)
            raise

    # ── Cerrar posición ───────────────────────────────────────────────────────

    def close_position(self, symbol: str, side: str, quantity: float) -> Dict[str, Any]:
        """
        Cierra toda la posición a precio de mercado.
        side = 'BUY' si posición es LONG, 'SELL' si es SHORT.
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        try:
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="MARKET",
                quantity=quantity,
                reduceOnly="true",
            )
            logger.info("Posición cerrada: %s | qty=%s", symbol, quantity)
            return order
        except BinanceAPIException as exc:
            error_logger.error("close_position(%s) error: %s", symbol, exc)
            raise

    # ── Consultar posiciones abiertas ─────────────────────────────────────────

    def get_open_positions(self, symbol: Optional[str] = None) -> list:
        """Retorna posiciones abiertas (cantidad != 0)."""
        try:
            positions = self._client.safe_call(
                self._client.client.futures_position_information,
                symbol=symbol,
            )
            return [p for p in positions if float(p.get("positionAmt", 0)) != 0]
        except BinanceAPIException as exc:
            error_logger.error("get_open_positions error: %s", exc)
            return []


# Instancia global
order_manager = OrderManager()
