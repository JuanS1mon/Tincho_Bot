"""
tools/execution_tool.py
=======================
Interfaz de alto nivel para ejecutar trades completos:
  1. Configura apalancamiento
  2. Abre posición market (LONG / SHORT)
  3. Coloca Stop Loss, Take Profit y Trailing Stop
  4. Registra la posición en el portafolio
"""
from __future__ import annotations

from typing import Optional

from exchange.order_manager import order_manager, OrderManager
from tools.portfolio_tool import portfolio_tool, Position, PortfolioTool
from tools.risk_tool import RiskParams
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


class ExecutionTool:
    """Ejecuta un trade completo con todos sus órdenes asociadas."""

    def __init__(
        self,
        order_mgr: OrderManager = order_manager,
        portfolio: PortfolioTool = portfolio_tool,
    ) -> None:
        self._orders = order_mgr
        self._portfolio = portfolio

    def execute(
        self,
        symbol: str,
        direction: str,
        risk_params: RiskParams,
        strategy: str = "",
        dry_run: bool = False,
    ) -> Optional[dict]:
        """
        Ejecuta el trade completo.
        
        dry_run=True → simula la ejecución sin enviar órdenes reales.
        Retorna dict con los IDs de las órdenes creadas, o None en caso de error.
        """
        if not risk_params.is_valid:
            logger.warning("execute: risk_params no válidos → abortando")
            return None

        logger.info(
            "[%s] Ejecutando %s en %s | qty=%.4f | capital=%.2f USDT | SL=%.4f | TP=%.4f",
            "DRY-RUN" if dry_run else "REAL",
            direction, symbol,
            risk_params.quantity, risk_params.capital_to_use,
            risk_params.stop_loss_price, risk_params.take_profit_price,
        )

        if dry_run:
            # En modo simulación registramos como si hubiera entrado al precio de SL/TP
            entry_price = risk_params.stop_loss_price  # placeholder
            self._register_position(symbol, direction, entry_price, risk_params, strategy, order_id="DRY_RUN")
            return {"mode": "dry_run", "symbol": symbol, "direction": direction}

        try:
            # 1. Configurar leverage
            self._orders.set_leverage(symbol, settings.leverage)

            # 2. Abrir posición
            side = "BUY" if direction == "LONG" else "SELL"
            main_order = (
                self._orders.open_long(symbol, risk_params.quantity)
                if direction == "LONG"
                else self._orders.open_short(symbol, risk_params.quantity)
            )
            entry_price = float(main_order.get("avgPrice", 0) or main_order.get("price", 0))
            order_id = str(main_order.get("orderId", ""))

            # 3. Stop Loss
            sl_order = self._orders.set_stop_loss(
                symbol, side, risk_params.stop_loss_price, risk_params.quantity
            )

            # 4. Take Profit
            tp_order = self._orders.set_take_profit(
                symbol, side, risk_params.take_profit_price, risk_params.quantity
            )

            # 5. Trailing Stop
            trailing_order = self._orders.set_trailing_stop(
                symbol, side, risk_params.trailing_callback_pct, risk_params.quantity
            )

            # 6. Registrar en portafolio
            self._register_position(symbol, direction, entry_price, risk_params, strategy, order_id)

            return {
                "main_order_id": order_id,
                "sl_order_id": sl_order.get("orderId"),
                "tp_order_id": tp_order.get("orderId"),
                "trailing_order_id": trailing_order.get("orderId"),
                "entry_price": entry_price,
                "symbol": symbol,
                "direction": direction,
            }

        except Exception as exc:
            error_logger.error("ExecutionTool.execute(%s %s) error: %s", direction, symbol, exc)
            return None

    def _register_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        risk_params: RiskParams,
        strategy: str,
        order_id: str,
    ) -> None:
        """Registra la posición en el portafolio."""
        position = Position(
            symbol=symbol,
            direction=direction,
            entry_price=entry_price,
            quantity=risk_params.quantity,
            capital_used=risk_params.capital_to_use,
            stop_loss=risk_params.stop_loss_price,
            take_profit=risk_params.take_profit_price,
            order_id=order_id,
        )
        self._portfolio.open_position(position)


# Instancia global
execution_tool = ExecutionTool()
