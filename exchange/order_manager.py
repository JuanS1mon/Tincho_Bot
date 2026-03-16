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

from decimal import Decimal, ROUND_DOWN
from typing import Any, Dict, Optional

from binance.exceptions import BinanceAPIException

from exchange.futures_client import futures_client
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class OrderManager:
    """Interfaz de alto nivel para operar en Binance Futures."""

    def __init__(self) -> None:
        self._client = futures_client
        self._symbol_rules_cache: Dict[str, Dict[str, Decimal]] = {}

    def _get_symbol_rules(self, symbol: str) -> Dict[str, Decimal]:
        """Obtiene stepSize/minQty de LOT_SIZE para normalizar quantities."""
        symbol = symbol.upper()
        cached = self._symbol_rules_cache.get(symbol)
        if cached is not None:
            return cached

        info = self._client.safe_call(self._client.client.futures_exchange_info)
        symbols = info.get("symbols", []) if isinstance(info, dict) else []
        for s in symbols:
            if s.get("symbol") != symbol:
                continue
            for f in s.get("filters", []):
                if f.get("filterType") == "LOT_SIZE":
                    rules = {
                        "step_size": Decimal(str(f.get("stepSize", "1"))),
                        "min_qty": Decimal(str(f.get("minQty", "0"))),
                    }
                    self._symbol_rules_cache[symbol] = rules
                    return rules
            break

        # Fallback defensivo si Binance no devuelve filtros del símbolo.
        fallback = {"step_size": Decimal("0.0001"), "min_qty": Decimal("0")}
        self._symbol_rules_cache[symbol] = fallback
        return fallback

    def _normalize_quantity(self, symbol: str, quantity: float) -> float:
        """Ajusta qty al múltiplo válido de stepSize usando redondeo hacia abajo."""
        q = Decimal(str(quantity))
        rules = self._get_symbol_rules(symbol)
        step = rules["step_size"]
        min_qty = rules["min_qty"]

        if step <= 0:
            return float(q)

        normalized = (q / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step
        if normalized < min_qty:
            normalized = min_qty
        return float(normalized)

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
            normalized_qty = self._normalize_quantity(symbol, quantity)
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=side,
                type="MARKET",
                quantity=normalized_qty,
            )
            logger.info(
                "Orden market ejecutada: %s %s | qty=%.8f (raw=%.8f) | orderId=%s",
                side, symbol, normalized_qty, quantity, order.get("orderId"),
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
            normalized_qty = self._normalize_quantity(symbol, quantity)
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="STOP_MARKET",
                stopPrice=round(stop_price, 2),
                quantity=normalized_qty,
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
            normalized_qty = self._normalize_quantity(symbol, quantity)
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="TAKE_PROFIT_MARKET",
                stopPrice=round(tp_price, 2),
                quantity=normalized_qty,
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
            normalized_qty = self._normalize_quantity(symbol, quantity)
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="TRAILING_STOP_MARKET",
                callbackRate=round(callback_rate, 1),
                quantity=normalized_qty,
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
            normalized_qty = self._normalize_quantity(symbol, quantity)
            order = self._client.safe_call(
                self._client.client.futures_create_order,
                symbol=symbol,
                side=close_side,
                type="MARKET",
                quantity=normalized_qty,
                reduceOnly="true",
            )
            logger.info("Posición cerrada: %s | qty=%.8f (raw=%.8f)", symbol, normalized_qty, quantity)
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
