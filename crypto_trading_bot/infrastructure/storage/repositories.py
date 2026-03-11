"""
Infrastructure - Repositories
================================
Repositorios CRUD para cada tabla de la base de datos.
Capa de abstracción sobre SQLite.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from config.logger import get_logger
from infrastructure.storage.database import Database

logger = get_logger(__name__)


class TradeRepository:
    """Repositorio para la tabla trades."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, trade: dict) -> int:
        """Guarda un trade y retorna su ID."""
        cursor = self.db.execute(
            """INSERT INTO trades 
            (timestamp, symbol, side, amount_usdt, quantity, price, 
             stop_loss, take_profit, status, mode, pnl, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade.get("timestamp", datetime.utcnow().isoformat()),
                trade["symbol"],
                trade["side"],
                trade["amount_usdt"],
                trade.get("quantity", 0),
                trade["price"],
                trade.get("stop_loss"),
                trade.get("take_profit"),
                trade["status"],
                trade.get("mode", "paper"),
                trade.get("pnl", 0),
                trade.get("order_id"),
            ),
        )
        return cursor.lastrowid

    def get_today_trades(self) -> List[dict]:
        """Obtiene todos los trades del día actual."""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        return self.db.fetchall(
            "SELECT * FROM trades WHERE timestamp LIKE ? ORDER BY timestamp DESC",
            (f"{today}%",),
        )

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Obtiene los trades más recientes."""
        return self.db.fetchall(
            "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (limit,)
        )

    def update_pnl(self, trade_id: int, pnl: float) -> None:
        """Actualiza el PnL de un trade cerrado."""
        self.db.execute(
            "UPDATE trades SET pnl = ?, closed_at = ? WHERE id = ?",
            (pnl, datetime.utcnow().isoformat(), trade_id),
        )


class MarketSnapshotRepository:
    """Repositorio para la tabla market_snapshots."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, snapshot: dict) -> int:
        """Guarda un snapshot de mercado."""
        cursor = self.db.execute(
            """INSERT INTO market_snapshots
            (timestamp, symbol, price, trend, momentum, volatility,
             volatility_state, volume_trend, rsi, macd_signal,
             sma_20, sma_50, ema_20, market_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.get("timestamp", datetime.utcnow().isoformat()),
                snapshot["symbol"],
                snapshot["price"],
                snapshot.get("trend"),
                snapshot.get("momentum"),
                snapshot.get("volatility"),
                snapshot.get("volatility_state"),
                snapshot.get("volume_trend"),
                snapshot.get("rsi"),
                snapshot.get("macd_signal"),
                snapshot.get("sma_20"),
                snapshot.get("sma_50"),
                snapshot.get("ema_20"),
                snapshot.get("market_state"),
            ),
        )
        return cursor.lastrowid

    def get_recent(self, symbol: str, limit: int = 100) -> List[dict]:
        """Obtiene snapshots recientes de un símbolo."""
        return self.db.fetchall(
            "SELECT * FROM market_snapshots WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        )


class AIDecisionRepository:
    """Repositorio para la tabla ai_decisions."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, decision: dict) -> int:
        """Guarda una decisión de la IA."""
        allocation = decision.get("allocation", {})
        cursor = self.db.execute(
            """INSERT INTO ai_decisions
            (timestamp, invest, confidence, capital_usage,
             allocation_btc, allocation_eth, market_state,
             reasoning, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                decision.get("timestamp", datetime.utcnow().isoformat()),
                1 if decision.get("invest") else 0,
                decision.get("confidence", 0),
                decision.get("capital_usage", 0),
                allocation.get("BTC", 0),
                allocation.get("ETH", 0),
                decision.get("market_state"),
                decision.get("reasoning"),
                json.dumps(decision.get("raw_response", {})),
            ),
        )
        return cursor.lastrowid

    def get_recent(self, limit: int = 50) -> List[dict]:
        """Obtiene decisiones recientes."""
        return self.db.fetchall(
            "SELECT * FROM ai_decisions ORDER BY id DESC LIMIT ?", (limit,)
        )


class SimulationResultRepository:
    """Repositorio para la tabla simulation_results."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, result: dict) -> int:
        """Guarda un resultado de simulación."""
        cursor = self.db.execute(
            """INSERT INTO simulation_results
            (timestamp, strategy, win_rate, profit, max_drawdown,
             sharpe_ratio, monte_carlo_median, monte_carlo_risk_ruin, approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                result.get("strategy", "default"),
                result.get("win_rate"),
                result.get("profit"),
                result.get("max_drawdown"),
                result.get("sharpe_ratio"),
                result.get("mc_median_return"),
                result.get("mc_risk_of_ruin"),
                1 if result.get("approved") else 0,
            ),
        )
        return cursor.lastrowid


class PortfolioHistoryRepository:
    """Repositorio para la tabla portfolio_history."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, snapshot: dict) -> int:
        """Guarda un snapshot del portafolio."""
        cursor = self.db.execute(
            """INSERT INTO portfolio_history
            (timestamp, balance_usdt, positions_value, total_capital, daily_pnl)
            VALUES (?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                snapshot["balance_usdt"],
                snapshot["positions_value"],
                snapshot["total_capital"],
                snapshot.get("daily_pnl", 0),
            ),
        )
        return cursor.lastrowid

    def get_history(self, limit: int = 1000) -> List[dict]:
        """Obtiene historial del portafolio."""
        return self.db.fetchall(
            "SELECT * FROM portfolio_history ORDER BY id DESC LIMIT ?", (limit,)
        )


class WhaleAlertRepository:
    """Repositorio para la tabla whale_alerts."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, alert: dict) -> int:
        """Guarda una alerta de whale."""
        cursor = self.db.execute(
            """INSERT INTO whale_alerts
            (timestamp, symbol, alert_type, side, quantity, price, total_value_usdt)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                alert["symbol"],
                alert["type"],
                alert.get("side"),
                alert["quantity"],
                alert["price"],
                alert.get("total_value_usdt", 0),
            ),
        )
        return cursor.lastrowid

    def get_recent(self, symbol: str = None, limit: int = 50) -> List[dict]:
        """Obtiene alertas recientes, opcionalmente filtradas por símbolo."""
        if symbol:
            return self.db.fetchall(
                "SELECT * FROM whale_alerts WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                (symbol, limit),
            )
        return self.db.fetchall(
            "SELECT * FROM whale_alerts ORDER BY id DESC LIMIT ?", (limit,)
        )


class OrderBookSnapshotRepository:
    """Repositorio para la tabla order_book_snapshots."""

    def __init__(self, db: Database):
        self.db = db

    def save(self, snapshot: dict) -> int:
        """Guarda un snapshot del order book."""
        cursor = self.db.execute(
            """INSERT INTO order_book_snapshots
            (timestamp, symbol, best_bid, best_ask, spread,
             bid_depth, ask_depth, imbalance_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                snapshot["symbol"],
                snapshot.get("best_bid"),
                snapshot.get("best_ask"),
                snapshot.get("spread"),
                snapshot.get("bid_depth"),
                snapshot.get("ask_depth"),
                snapshot.get("imbalance_ratio"),
            ),
        )
        return cursor.lastrowid


class IndicatorWeightRepository:
    """Repositorio para la tabla indicator_weights (Learning Engine)."""

    def __init__(self, db: Database):
        self.db = db
        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Inicializa los pesos por defecto si no existen."""
        default_indicators = ["RSI", "MACD", "SMA", "EMA", "Volatility", "Volume"]
        for indicator in default_indicators:
            existing = self.db.fetchone(
                "SELECT * FROM indicator_weights WHERE indicator = ?",
                (indicator,),
            )
            if not existing:
                self.db.execute(
                    """INSERT INTO indicator_weights (indicator, weight, wins, losses, last_updated)
                    VALUES (?, 1.0, 0, 0, ?)""",
                    (indicator, datetime.utcnow().isoformat()),
                )

    def get_all_weights(self) -> Dict[str, float]:
        """Retorna todos los pesos de indicadores."""
        rows = self.db.fetchall("SELECT indicator, weight FROM indicator_weights")
        return {row["indicator"]: row["weight"] for row in rows}

    def update_weight(self, indicator: str, won: bool, adjustment: float = 0.05) -> None:
        """
        Actualiza el peso de un indicador basado en si acertó o no.
        
        Args:
            indicator: Nombre del indicador.
            won: True si el indicador acertó en la predicción.
            adjustment: Magnitud del ajuste (default 0.05).
        """
        if won:
            self.db.execute(
                """UPDATE indicator_weights 
                SET weight = MIN(weight + ?, 2.0), 
                    wins = wins + 1,
                    last_updated = ?
                WHERE indicator = ?""",
                (adjustment, datetime.utcnow().isoformat(), indicator),
            )
        else:
            self.db.execute(
                """UPDATE indicator_weights 
                SET weight = MAX(weight - ?, 0.1), 
                    losses = losses + 1,
                    last_updated = ?
                WHERE indicator = ?""",
                (adjustment, datetime.utcnow().isoformat(), indicator),
            )

    def get_stats(self) -> List[dict]:
        """Retorna estadísticas completas de todos los indicadores."""
        return self.db.fetchall(
            "SELECT * FROM indicator_weights ORDER BY weight DESC"
        )
