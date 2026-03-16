"""
tools/portfolio_tool.py
=======================
Gestiona el estado del portafolio en tiempo real:
  - Capital disponible
  - Posiciones abiertas
  - PnL realizado y no realizado
  - Historial de trades
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time

from config.settings import settings
from config.logger import trading_logger as logger


@dataclass
class Position:
    symbol: str
    direction: str           # LONG | SHORT
    entry_price: float
    quantity: float
    capital_used: float
    stop_loss: float
    take_profit: float
    entry_time: float = field(default_factory=time.time)
    order_id: Optional[str] = None

    def unrealized_pnl(self, current_price: float) -> float:
        """PnL no realizado basado en el precio actual."""
        if self.direction == "LONG":
            return (current_price - self.entry_price) * self.quantity
        else:  # SHORT
            return (self.entry_price - current_price) * self.quantity


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    strategy: str
    duration_seconds: float
    timestamp: float = field(default_factory=time.time)


class PortfolioTool:
    """Seguimiento en tiempo real del portafolio y posiciones."""

    def __init__(self) -> None:
        self.capital: float = settings.initial_capital
        self.initial_capital: float = settings.initial_capital
        self.positions: Dict[str, Position] = {}  # symbol → Position
        self.trade_history: List[TradeRecord] = []
        self.total_trades: int = 0
        self.winning_trades: int = 0

    def sync_from_exchange(self, force: bool = False) -> None:
        """
        Sincroniza el capital con el saldo USDT real de la cuenta Futures.
        En testnet se omite: la API del testnet no soporta futures_account_balance.
        """
        if settings.binance_testnet:
            logger.debug("sync_from_exchange: omitido en testnet.")
            return
        from exchange.market_fetcher import market_fetcher
        real_balance = market_fetcher.get_usdt_balance()
        if real_balance is not None:
            if self.positions and not force:
                # Hay posiciones abiertas: solo actualizamos initial_capital
                # (el capital operativo lo gestiona close_position)
                logger.info(
                    "sync_from_exchange: posiciones abiertas, solo actualizando referencia. "
                    "Binance=%.4f USDT", real_balance,
                )
            else:
                self.capital = real_balance
                self.initial_capital = real_balance
                logger.info(
                    "Capital sincronizado desde Binance Futures: %.4f USDT", real_balance,
                )
                if real_balance == 0:
                    logger.warning(
                        "Saldo Futures en USDT es 0.0000. Si querés operar, transferí fondos a USDT-M Futures."
                    )
        else:
            logger.warning(
                "Balance Binance no disponible. Usando capital actual: %.2f USDT. "
                "[Acción requerida] En Binance → API Management → "
                "habilitá 'Enable Futures' y desactivá restricción de IP para esta key.",
                self.capital,
            )

    # ── Capital ───────────────────────────────────────────────────────────────

    @property
    def available_capital(self) -> float:
        """Capital total no comprometido en posiciones abiertas."""
        committed = sum(p.capital_used for p in self.positions.values())
        return max(0, self.capital - committed)

    def available_capital_for_symbol(self, symbol: str) -> float:
        """
        Capital disponible para un símbolo específico.

        El capital total se divide equitativamente entre todos los símbolos
        configurados (50%/50% con 2 símbolos). Cada símbolo opera solo con
        su porción, permitiendo crecimiento incremental independiente.

        Ejemplo: capital=200 USDT, 2 símbolos → 100 USDT por símbolo.
        Si BTC ya tiene comprometidos 30 USDT → BTC disponible = 70 USDT.
        """
        num_symbols = max(1, len(settings.symbols))
        symbol_allocation = self.capital / num_symbols
        committed = self.positions[symbol].capital_used if symbol in self.positions else 0.0
        return max(0.0, symbol_allocation - committed)

    def symbol_allocation(self, symbol: str) -> float:
        """Capital total asignado al símbolo (sin descontar posiciones abiertas)."""
        num_symbols = max(1, len(settings.symbols))
        return self.capital / num_symbols

    @property
    def total_equity(self) -> float:
        """Capital total (el capital crece con cada trade ganador vía close_position)."""
        return self.capital

    @property
    def win_rate(self) -> float:
        return self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0

    @property
    def total_pnl(self) -> float:
        return self.capital - self.initial_capital

    # ── Posiciones ────────────────────────────────────────────────────────────

    def open_position(self, position: Position) -> None:
        """Registra una nueva posición abierta."""
        self.positions[position.symbol] = position
        logger.info(
            "Posición abierta: %s %s @ %.4f | qty=%.4f | capital=%.2f USDT",
            position.direction, position.symbol,
            position.entry_price, position.quantity, position.capital_used,
        )

    def close_position(self, symbol: str, exit_price: float, strategy: str = "") -> Optional[TradeRecord]:
        """Cierra una posición y registra el resultado."""
        position = self.positions.pop(symbol, None)
        if position is None:
            logger.warning("close_position: no hay posición abierta para %s", symbol)
            return None

        pnl = position.unrealized_pnl(exit_price)
        pnl_pct = pnl / position.capital_used * 100 if position.capital_used > 0 else 0
        duration = time.time() - position.entry_time

        # Actualizar capital
        self.capital += pnl
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1

        record = TradeRecord(
            symbol=symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=position.quantity,
            pnl=round(pnl, 4),
            pnl_pct=round(pnl_pct, 2),
            strategy=strategy,
            duration_seconds=round(duration, 1),
        )
        self.trade_history.append(record)

        logger.info(
            "Posición cerrada: %s %s | PnL=%.4f USDT (%.2f%%) | capital=%.2f USDT",
            position.direction, symbol, pnl, pnl_pct, self.capital,
        )
        return record

    def has_open_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        return self.positions.get(symbol)

    def get_state_dict(self) -> dict:
        """Retorna el estado actual del portafolio como dict serializable."""
        return {
            "capital": round(self.capital, 4),
            "available_capital": round(self.available_capital, 4),
            "initial_capital": self.initial_capital,
            "total_pnl": round(self.total_pnl, 4),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "win_rate": round(self.win_rate, 4),
            "open_positions": len(self.positions),
            "positions": {
                sym: {
                    "direction": p.direction,
                    "entry_price": p.entry_price,
                    "quantity": p.quantity,
                    "capital_used": p.capital_used,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for sym, p in self.positions.items()
            },
        }


# Instancia global
portfolio_tool = PortfolioTool()
