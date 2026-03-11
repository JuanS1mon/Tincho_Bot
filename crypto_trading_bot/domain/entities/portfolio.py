"""
Domain Entity - Portfolio
=========================
Gestión dinámica del portafolio.
Recalcula capital_actual = balance_USDT + valor_USDT de posiciones abiertas.
Persiste historial de equity en data/equity_history.csv.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from config.settings import settings, BASE_DIR
from config.logger import get_logger

logger = get_logger(__name__)

# Ruta del historial de equity
EQUITY_HISTORY_PATH = BASE_DIR / "data" / "equity_history.csv"


@dataclass
class Position:
    """Representa una posición abierta en un activo."""
    symbol: str
    quantity: float
    entry_price: float
    entry_time: datetime = field(default_factory=datetime.utcnow)

    @property
    def entry_value_usdt(self) -> float:
        """Valor en USDT al momento de la entrada."""
        return self.quantity * self.entry_price

    def current_value_usdt(self, current_price: float) -> float:
        """Valor actual en USDT de la posición."""
        return self.quantity * current_price

    def pnl(self, current_price: float) -> float:
        """Ganancia/pérdida no realizada en USDT."""
        return self.current_value_usdt(current_price) - self.entry_value_usdt

    def pnl_percent(self, current_price: float) -> float:
        """Ganancia/pérdida porcentual."""
        if self.entry_value_usdt == 0:
            return 0.0
        return self.pnl(current_price) / self.entry_value_usdt


@dataclass
class Portfolio:
    """
    Portafolio dinámico del bot de trading.
    
    El capital se recalcula en cada ciclo a partir del balance real
    de USDT más el valor de las posiciones abiertas.
    """
    balance_usdt: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    daily_pnl: float = 0.0
    daily_start_capital: float = 0.0
    last_update: Optional[datetime] = None

    def update_balance(self, balance_usdt: float, prices: Dict[str, float]) -> None:
        """
        Actualiza el balance y recalcula capital total.
        
        Args:
            balance_usdt: Balance libre en USDT desde Binance.
            prices: Diccionario {symbol: price} con precios actuales.
        """
        self.balance_usdt = balance_usdt
        self.last_update = datetime.utcnow()

        capital = self.capital_actual(prices)
        logger.info(
            f"Portfolio actualizado: balance_USDT={balance_usdt:.2f}, "
            f"capital_total={capital:.2f}, posiciones={len(self.positions)}"
        )

    def capital_actual(self, prices: Dict[str, float]) -> float:
        """
        Calcula el capital actual total.
        capital_actual = balance_USDT + valor_USDT de todas las posiciones.
        
        Args:
            prices: Diccionario {symbol: price} con precios actuales.
        """
        positions_value = sum(
            pos.current_value_usdt(prices.get(pos.symbol, pos.entry_price))
            for pos in self.positions.values()
        )
        return self.balance_usdt + positions_value

    def positions_value_usdt(self, prices: Dict[str, float]) -> float:
        """Valor total de posiciones abiertas en USDT."""
        return sum(
            pos.current_value_usdt(prices.get(pos.symbol, pos.entry_price))
            for pos in self.positions.values()
        )

    def add_position(self, symbol: str, quantity: float, price: float) -> None:
        """Agrega o incrementa una posición."""
        if symbol in self.positions:
            # Promedio de precio de entrada
            existing = self.positions[symbol]
            total_qty = existing.quantity + quantity
            avg_price = (
                (existing.quantity * existing.entry_price + quantity * price) / total_qty
            )
            existing.quantity = total_qty
            existing.entry_price = avg_price
        else:
            self.positions[symbol] = Position(
                symbol=symbol, quantity=quantity, entry_price=price
            )
        logger.info(f"Posición añadida: {symbol} qty={quantity:.6f} @ {price:.2f}")

    def close_position(self, symbol: str, current_price: float) -> Optional[float]:
        """
        Cierra una posición y retorna el PnL realizado.
        
        Returns:
            PnL en USDT si la posición existía, None si no.
        """
        if symbol not in self.positions:
            logger.warning(f"No hay posición abierta para {symbol}")
            return None

        position = self.positions.pop(symbol)
        pnl = position.pnl(current_price)
        self.daily_pnl += pnl

        logger.info(
            f"Posición cerrada: {symbol} PnL={pnl:.2f} USDT "
            f"({position.pnl_percent(current_price):.2%})"
        )
        return pnl

    def daily_loss_percent(self, prices: Dict[str, float]) -> float:
        """Calcula la pérdida diaria como porcentaje del capital inicial del día."""
        if self.daily_start_capital <= 0:
            return 0.0
        current = self.capital_actual(prices)
        loss = (self.daily_start_capital - current) / self.daily_start_capital
        return max(0.0, loss)  # Solo retorna pérdida, no ganancia

    def reset_daily_tracking(self, prices: Dict[str, float]) -> None:
        """Resetea el tracking diario. Llamar al inicio de cada día."""
        self.daily_start_capital = self.capital_actual(prices)
        self.daily_pnl = 0.0
        logger.info(f"Tracking diario reseteado. Capital inicial: {self.daily_start_capital:.2f}")

    def save_equity_snapshot(self, prices: Dict[str, float]) -> None:
        """Guarda un snapshot del capital actual en equity_history.csv."""
        EQUITY_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)

        file_exists = EQUITY_HISTORY_PATH.exists()
        capital = self.capital_actual(prices)

        with open(EQUITY_HISTORY_PATH, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "capital", "balance_usdt", "positions_value"])
            writer.writerow([
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                f"{capital:.2f}",
                f"{self.balance_usdt:.2f}",
                f"{self.positions_value_usdt(prices):.2f}",
            ])

        logger.debug(f"Equity snapshot guardado: {capital:.2f}")

    def to_dict(self, prices: Dict[str, float]) -> dict:
        """Serializa el estado del portafolio como diccionario."""
        return {
            "balance_usdt": round(self.balance_usdt, 2),
            "capital_actual": round(self.capital_actual(prices), 2),
            "positions_value": round(self.positions_value_usdt(prices), 2),
            "positions": {
                symbol: {
                    "quantity": pos.quantity,
                    "entry_price": pos.entry_price,
                    "current_price": prices.get(symbol, pos.entry_price),
                    "pnl": round(pos.pnl(prices.get(symbol, pos.entry_price)), 2),
                    "pnl_percent": round(
                        pos.pnl_percent(prices.get(symbol, pos.entry_price)), 4
                    ),
                }
                for symbol, pos in self.positions.items()
            },
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_loss_percent": round(self.daily_loss_percent(prices), 4),
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }
