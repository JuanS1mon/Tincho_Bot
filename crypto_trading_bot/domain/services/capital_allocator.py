"""
Domain Service - Capital Allocator
====================================
Distribuye el capital entre BTC y ETH según la decisión de la IA,
respetando los límites del RiskManager.
"""

from dataclasses import dataclass
from typing import Dict, List

from config.logger import get_logger
from config.settings import settings
from domain.entities.portfolio import Portfolio
from domain.entities.trade_signal import TradeSignal
from domain.services.risk_manager import RiskManager, RiskValidation

logger = get_logger(__name__)


@dataclass
class TradeOrder:
    """Orden de trade individual lista para ejecutar."""
    symbol: str
    side: str  # "BUY" o "SELL"
    amount_usdt: float
    quantity: float  # Cantidad del activo a comprar/vender
    price: float  # Precio actual al momento de calcular
    stop_loss: float
    take_profit: float


class CapitalAllocator:
    """
    Distribuye el capital entre activos según la señal de la IA.
    Genera órdenes concretas respetando los límites de riesgo.
    """

    def __init__(self):
        self.risk_manager = RiskManager()

    def allocate(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        prices: Dict[str, float],
        risk_validation: RiskValidation,
    ) -> List[TradeOrder]:
        """
        Genera las órdenes de trading concretas.
        
        Args:
            signal: Señal de trading validada.
            portfolio: Estado del portafolio.
            prices: Precios actuales {symbol: price}.
            risk_validation: Resultado de la validación de riesgo.
            
        Returns:
            Lista de TradeOrder listas para ejecutar.
        """
        if not risk_validation.approved:
            logger.info(f"Allocator: Sin órdenes - {risk_validation.reason}")
            return []

        capital = portfolio.capital_actual(prices)
        usable_capital = capital * risk_validation.adjusted_capital_usage

        logger.info(
            f"Allocator: Capital total={capital:.2f}, "
            f"usable={usable_capital:.2f} ({risk_validation.adjusted_capital_usage:.0%})"
        )

        orders = []

        for asset, alloc_pct in signal.allocation.items():
            # Mapear nombre del activo a símbolo de Binance
            symbol = f"{asset}USDT"
            if symbol not in prices:
                logger.warning(f"Precio no disponible para {symbol}, omitiendo...")
                continue

            price = prices[symbol]
            if price <= 0:
                logger.warning(f"Precio inválido para {symbol}: {price}")
                continue

            # Calcular monto en USDT y cantidad del activo
            amount_usdt = usable_capital * alloc_pct
            quantity = amount_usdt / price

            # Calcular stop-loss y take-profit
            sl_price, tp_price = self.risk_manager.calculate_stop_take(price)

            # Mínimo 10 USDT por orden
            if amount_usdt < 10.0:
                logger.info(
                    f"Orden {symbol} omitida: monto={amount_usdt:.2f} < 10 USDT"
                )
                continue

            order = TradeOrder(
                symbol=symbol,
                side="BUY",
                amount_usdt=round(amount_usdt, 2),
                quantity=quantity,
                price=price,
                stop_loss=sl_price,
                take_profit=tp_price,
            )
            orders.append(order)

            logger.info(
                f"Orden generada: {symbol} BUY {amount_usdt:.2f} USDT "
                f"(qty={quantity:.6f} @ {price:.2f}) "
                f"SL={sl_price:.2f} TP={tp_price:.2f}"
            )

        return orders

    def calculate_rebalance_orders(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        prices: Dict[str, float],
    ) -> List[TradeOrder]:
        """
        Calcula órdenes de rebalanceo si ya hay posiciones abiertas.
        Compara la distribución actual con la deseada.
        
        Returns:
            Lista de órdenes para rebalancear el portafolio.
        """
        orders = []
        capital = portfolio.capital_actual(prices)

        for asset, target_pct in signal.allocation.items():
            symbol = f"{asset}USDT"
            price = prices.get(symbol, 0)
            if price <= 0:
                continue

            # Valor actual de la posición
            current_value = 0.0
            if symbol in portfolio.positions:
                current_value = portfolio.positions[symbol].current_value_usdt(price)

            # Valor objetivo
            target_value = capital * signal.capital_usage * target_pct
            diff = target_value - current_value

            # Solo rebalancear si la diferencia es significativa (> 5%)
            if abs(diff) < capital * 0.05 or abs(diff) < 10:
                continue

            side = "BUY" if diff > 0 else "SELL"
            amount_usdt = abs(diff)
            quantity = amount_usdt / price
            sl_price, tp_price = self.risk_manager.calculate_stop_take(price)

            order = TradeOrder(
                symbol=symbol,
                side=side,
                amount_usdt=round(amount_usdt, 2),
                quantity=quantity,
                price=price,
                stop_loss=sl_price,
                take_profit=tp_price,
            )
            orders.append(order)

            logger.info(
                f"Rebalanceo: {symbol} {side} {amount_usdt:.2f} USDT "
                f"(actual={current_value:.2f}, objetivo={target_value:.2f})"
            )

        return orders
