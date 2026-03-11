"""
Infrastructure - Database
==========================
Inicialización y gestión de SQLite.
Crea las tablas necesarias para el bot de trading:
  - trades
  - market_snapshots
  - ai_decisions
  - simulation_results
  - portfolio_history
  - whale_alerts
  - order_book_snapshots
  - indicator_weights
"""

import sqlite3
from pathlib import Path

from config.logger import get_logger
from config.settings import settings, BASE_DIR

logger = get_logger(__name__)


class Database:
    """Gestor de base de datos SQLite para el bot de trading."""

    def __init__(self):
        self.db_path = BASE_DIR / settings.DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = None
        self._connect()
        self._create_tables()

    def _connect(self) -> None:
        """Establece conexión con la base de datos SQLite."""
        try:
            self.connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
            )
            self.connection.row_factory = sqlite3.Row
            self.connection.execute("PRAGMA journal_mode=WAL")
            logger.info(f"💾 Base de datos conectada: {self.db_path}")
        except Exception as e:
            logger.error(f"Error conectando a base de datos: {e}")
            raise

    def _create_tables(self) -> None:
        """Crea todas las tablas necesarias si no existen."""
        cursor = self.connection.cursor()

        # --- Trades ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL,
                pnl REAL DEFAULT 0,
                closed_at TEXT,
                order_id TEXT
            )
        """)

        # --- Market Snapshots ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                trend TEXT,
                momentum TEXT,
                volatility REAL,
                volatility_state TEXT,
                volume_trend TEXT,
                rsi REAL,
                macd_signal TEXT,
                sma_20 REAL,
                sma_50 REAL,
                ema_20 REAL,
                market_state TEXT
            )
        """)

        # --- AI Decisions ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                invest INTEGER NOT NULL,
                confidence REAL NOT NULL,
                capital_usage REAL NOT NULL,
                allocation_btc REAL DEFAULT 0,
                allocation_eth REAL DEFAULT 0,
                market_state TEXT,
                reasoning TEXT,
                raw_response TEXT
            )
        """)

        # --- Simulation Results ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS simulation_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                strategy TEXT,
                win_rate REAL,
                profit REAL,
                max_drawdown REAL,
                sharpe_ratio REAL,
                monte_carlo_median REAL,
                monte_carlo_risk_ruin REAL,
                approved INTEGER
            )
        """)

        # --- Portfolio History ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                balance_usdt REAL NOT NULL,
                positions_value REAL NOT NULL,
                total_capital REAL NOT NULL,
                daily_pnl REAL DEFAULT 0
            )
        """)

        # --- Whale Alerts ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS whale_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                side TEXT,
                quantity REAL NOT NULL,
                price REAL NOT NULL,
                total_value_usdt REAL
            )
        """)

        # --- Order Book Snapshots ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_book_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                best_bid REAL,
                best_ask REAL,
                spread REAL,
                bid_depth REAL,
                ask_depth REAL,
                imbalance_ratio REAL
            )
        """)

        # --- Indicator Weights (Learning Engine) ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS indicator_weights (
                indicator TEXT PRIMARY KEY,
                weight REAL NOT NULL DEFAULT 1.0,
                wins INTEGER DEFAULT 0,
                losses INTEGER DEFAULT 0,
                last_updated TEXT
            )
        """)

        self.connection.commit()
        logger.info("📊 Tablas de base de datos verificadas/creadas")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """Ejecuta una query con parámetros."""
        try:
            cursor = self.connection.cursor()
            cursor.execute(query, params)
            self.connection.commit()
            return cursor
        except Exception as e:
            logger.error(f"Error ejecutando query: {e}\nQuery: {query}")
            raise

    def fetchall(self, query: str, params: tuple = ()) -> list:
        """Ejecuta una query y retorna todas las filas."""
        cursor = self.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def fetchone(self, query: str, params: tuple = ()) -> dict:
        """Ejecuta una query y retorna una fila."""
        cursor = self.execute(query, params)
        row = cursor.fetchone()
        return dict(row) if row else {}

    def close(self) -> None:
        """Cierra la conexión a la base de datos."""
        if self.connection:
            self.connection.close()
            logger.info("Base de datos cerrada")
