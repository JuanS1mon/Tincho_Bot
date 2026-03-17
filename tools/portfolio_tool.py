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
    peak_unrealized_pnl: float = 0.0
    peak_unrealized_pnl_pct: float = 0.0

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

    # Drawdown máximo tolerado desde el pico de sesión.
    # Se usa como referencia histórica/documental; el high-watermark dinámico
    # ya no limita la ganancia máxima que puede correr.
    CIRCUIT_BREAKER_THRESHOLD = -0.15
    # Número de pérdidas consecutivas que activa el enfriamiento.
    MAX_CONSECUTIVE_LOSSES = 3
    # Piso mínimo: permite hasta este % de drawdown antes de tener ganancias.
    # Evita que el CB se dispare en la primera micro-pérdida del día.
    CIRCUIT_BREAKER_FLOOR = 0.05
    # Si una operación llegó a un pico de ganancia, se cierra cuando retrocede
    # más de este porcentaje desde ese pico (profit lock dinámico por posición).
    PROFIT_LOCK_RETRACE_PCT = settings.profit_lock_retrace_pct

    def __init__(self) -> None:
        self.capital: float = settings.initial_capital
        self.initial_capital: float = settings.initial_capital
        self.positions: Dict[str, Position] = {}  # symbol → Position
        self.trade_history: List[TradeRecord] = []
        self.total_trades: int = 0
        self.winning_trades: int = 0
        # Protecciones anti-pérdida
        self._session_started: bool = False
        self.session_start_capital: float = 0.0   # snapshot al primer sync real
        self.session_peak_capital: float = 0.0    # máximo histórico de la sesión
        self.consecutive_losses: int = 0          # reinicia en cada trade ganador

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
                # Primer sync real: tomar snapshot de capital de sesión.
                if not self._session_started and real_balance > 0:
                    self.session_start_capital = real_balance
                    self.session_peak_capital = real_balance
                    self._session_started = True
                    logger.info("Session capital snapshot: %.4f USDT", real_balance)
                # Actualizar el máximo histórico (high-watermark) si el balance subió.
                elif real_balance > self.session_peak_capital:
                    logger.info(
                        "Nuevo máximo de sesión: %.4f USDT (anterior=%.4f)",
                        real_balance, self.session_peak_capital,
                    )
                    self.session_peak_capital = real_balance
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

        Política actual: el capital es global y compartido. El bot decide cuánto
        asignar a cada operación usando el capital total disponible, no una cuota
        fija por símbolo.

        Mientras no exista una restricción adicional por símbolo, devolvemos el
        capital total libre del portafolio.
        """
        return self.available_capital

    def symbol_allocation(self, symbol: str) -> float:
        """Capital total elegible para una nueva posición en ese símbolo."""
        return self.capital

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

    @property
    def closed_trades_pnl(self) -> float:
        """PnL realizado total de todos los trades cerrados."""
        return sum(t.pnl for t in self.trade_history)

    @property
    def closed_trades_pnl_pct(self) -> float:
        """PnL realizado como porcentaje del capital inicial."""
        if self.initial_capital <= 0:
            return 0.0
        return (self.closed_trades_pnl / self.initial_capital) * 100

    # ── Posiciones ────────────────────────────────────────────────────────────

    def open_position(self, position: Position) -> None:
        """Registra una nueva posición abierta."""
        position.peak_unrealized_pnl = 0.0
        position.peak_unrealized_pnl_pct = 0.0
        self.positions[position.symbol] = position
        logger.info(
            "Posición abierta: %s %s @ %.4f | qty=%.4f | capital=%.2f USDT",
            position.direction, position.symbol,
            position.entry_price, position.quantity, position.capital_used,
        )

    def update_position_peak(self, symbol: str, current_price: float) -> None:
        """Actualiza el pico de PnL no realizado para una posición abierta."""
        pos = self.positions.get(symbol)
        if pos is None:
            return

        pnl_now = pos.unrealized_pnl(current_price)
        if pnl_now > pos.peak_unrealized_pnl:
            pos.peak_unrealized_pnl = pnl_now

        if pos.capital_used > 0:
            pnl_pct_now = pnl_now / pos.capital_used
            if pnl_pct_now > pos.peak_unrealized_pnl_pct:
                pos.peak_unrealized_pnl_pct = pnl_pct_now

    def profit_lock_state(self, symbol: str, current_price: float) -> tuple[bool, float, float, float]:
        """
        Evalúa si debe cerrarse por retroceso desde el pico de ganancia.

        Retorna:
          (triggered, pnl_actual, peak_pnl, piso_permitido)
        """
        pos = self.positions.get(symbol)
        if pos is None:
            return False, 0.0, 0.0, 0.0

        self.update_position_peak(symbol, current_price)

        pnl_now = pos.unrealized_pnl(current_price)
        peak_pnl = pos.peak_unrealized_pnl
        if peak_pnl <= 0:
            return False, pnl_now, peak_pnl, 0.0

        floor_pnl = peak_pnl * (1.0 - self.get_profit_lock_retrace_pct())
        triggered = pnl_now <= floor_pnl
        return triggered, pnl_now, peak_pnl, floor_pnl

    def get_profit_lock_retrace_pct(self) -> float:
        """Retorna retrace dinámico para profit lock (prioriza parámetros vivos del agente)."""
        try:
            from agent.parameters_manager import parameters_manager
            val = float(getattr(parameters_manager.params, "profit_lock_retrace_pct", self.PROFIT_LOCK_RETRACE_PCT) or 0)
        except Exception:
            val = float(self.PROFIT_LOCK_RETRACE_PCT)
        # Guardas defensivas para evitar valores extremos por datos corruptos
        return max(0.01, min(0.90, val))

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
        # Actualizar high-watermark con el capital post-trade.
        if self.capital > self.session_peak_capital:
            self.session_peak_capital = self.capital
        self.total_trades += 1
        if pnl > 0:
            self.winning_trades += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

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

    @property
    def session_drawdown_pct(self) -> float:
        """Drawdown desde el inicio de sesión (negativo = pérdida)."""
        if self.session_start_capital <= 0:
            return 0.0
        return (self.capital - self.session_start_capital) / self.session_start_capital

    @property
    def circuit_breaker_active(self) -> bool:
                """
                True si el drawdown desde el pico de sesión supera el límite permitido.

                Lógica dinámica (high-watermark):
                    - Rastreamos el capital máximo de la sesión (session_peak_capital).
                    - La pérdida máxima tolerada = ganancia_acumulada desde el inicio.
                    - Piso: siempre se permiten al menos 5% de drawdown antes de tener ganancias
                        para evitar que el CB se dispare en la primera micro-pérdida.
                    - No hay cap superior: si llegás a +25%, el breaker puede tolerar
                        hasta 25% desde el pico sin dejarte por debajo del capital inicial.

                Ejemplos:
                    Ganaste  0% → toleramos hasta 5% de caída desde pico.
                    Ganaste  3% → toleramos hasta 5% (piso) desde pico.
                    Ganaste  8% → toleramos hasta 8% desde pico (nunca volverás a pérdida).
                      Ganaste 15% → toleramos hasta 15% desde pico.
                      Ganaste 20% → toleramos hasta 20% desde pico.
                """
                if self.session_peak_capital <= 0 or self.session_start_capital <= 0:
                        return False

                # Ganancia acumulada desde el inicio hasta el pico.
                gain_pct = (self.session_peak_capital - self.session_start_capital) / self.session_start_capital

                # Límite: toda la ganancia acumulada desde el inicio,
                # con un piso del 5% para cuando aún no hay ganancias significativas.
                allowed_dd = max(self.CIRCUIT_BREAKER_FLOOR, gain_pct)

                # Drawdown actual desde el pico.
                dd_from_peak = (self.session_peak_capital - self.capital) / self.session_peak_capital

                if dd_from_peak >= allowed_dd:
                        logger.warning(
                                "🚨 Circuit breaker: pico=%.2f USDT | actual=%.2f USDT | "
                                "caída=%.1f%% | límite=%.1f%% (ganancia acumulada=%.1f%%)",
                                self.session_peak_capital, self.capital,
                                dd_from_peak * 100, allowed_dd * 100, gain_pct * 100,
                        )
                        return True
                return False

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
            "closed_trades_pnl": round(self.closed_trades_pnl, 4),
            "closed_trades_pnl_pct": round(self.closed_trades_pnl_pct, 2),
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
                    "peak_unrealized_pnl": round(p.peak_unrealized_pnl, 4),
                    "peak_unrealized_pnl_pct": round(p.peak_unrealized_pnl_pct, 4),
                }
                for sym, p in self.positions.items()
            },
        }


# Instancia global
portfolio_tool = PortfolioTool()
