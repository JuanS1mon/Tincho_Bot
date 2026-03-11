"""
Config - Settings
=================
Configuración centralizada del sistema.
Carga todas las variables desde .env y las expone como propiedades tipadas.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
from typing import List

# Cargar .env desde la raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    """Configuración global del bot de trading, cargada desde .env."""

    # ----------------------------------------------------------------
    # Binance
    # ----------------------------------------------------------------
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET_KEY: str = os.getenv("BINANCE_SECRET_KEY", "")
    BINANCE_TESTNET: bool = os.getenv("BINANCE_TESTNET", "true").lower() == "true"

    # ----------------------------------------------------------------
    # AI
    # ----------------------------------------------------------------
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "deepseek")
    AI_MODEL: str = os.getenv("AI_MODEL", "deepseek-chat")
    AI_BASE_URL: str = os.getenv("AI_BASE_URL", "https://api.deepseek.com")
    AI_API_KEY: str = os.getenv("AI_API_KEY", "")

    # ----------------------------------------------------------------
    # Capital
    # ----------------------------------------------------------------
    INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "100"))

    # ----------------------------------------------------------------
    # Risk Management
    # ----------------------------------------------------------------
    MAX_CAPITAL_USAGE: float = float(os.getenv("MAX_CAPITAL_USAGE", "0.7"))
    MAX_CAPITAL_PER_TRADE: float = float(os.getenv("MAX_CAPITAL_PER_TRADE", "0.35"))
    STOP_LOSS: float = float(os.getenv("STOP_LOSS", "0.03"))
    TAKE_PROFIT: float = float(os.getenv("TAKE_PROFIT", "0.07"))
    DAILY_MAX_LOSS: float = float(os.getenv("DAILY_MAX_LOSS", "0.05"))

    # ----------------------------------------------------------------
    # Market
    # ----------------------------------------------------------------
    SYMBOLS: List[str] = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT").split(",")
    ANALYSIS_DAYS: int = int(os.getenv("ANALYSIS_DAYS", "30"))
    INTERVALS: List[str] = [
        os.getenv("INTERVAL_1", "1h"),
        os.getenv("INTERVAL_2", "4h"),
        os.getenv("INTERVAL_3", "1d"),
    ]

    # ----------------------------------------------------------------
    # Execution
    # ----------------------------------------------------------------
    TRADING_MODE: str = os.getenv("TRADING_MODE", "paper")
    EXECUTION_INTERVAL_MINUTES: int = int(os.getenv("EXECUTION_INTERVAL_MINUTES", "15"))

    # ----------------------------------------------------------------
    # Simulation
    # ----------------------------------------------------------------
    ENABLE_BACKTEST: bool = os.getenv("ENABLE_BACKTEST", "true").lower() == "true"
    MONTE_CARLO_SIMULATIONS: int = int(os.getenv("MONTE_CARLO_SIMULATIONS", "1000"))
    MIN_WIN_RATE: float = float(os.getenv("MIN_WIN_RATE", "0.55"))

    # ----------------------------------------------------------------
    # Database
    # ----------------------------------------------------------------
    DB_TYPE: str = os.getenv("DB_TYPE", "sqlite")
    DB_PATH: str = os.getenv("DB_PATH", "data/trading.db")

    # ----------------------------------------------------------------
    # Logs
    # ----------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ----------------------------------------------------------------
    # Advanced: Whale Detection
    # ----------------------------------------------------------------
    WHALE_THRESHOLD_BTC: float = float(os.getenv("WHALE_THRESHOLD_BTC", "5.0"))
    WHALE_THRESHOLD_ETH: float = float(os.getenv("WHALE_THRESHOLD_ETH", "50.0"))
    WHALE_STD_MULTIPLIER: float = float(os.getenv("WHALE_STD_MULTIPLIER", "2.0"))

    # ----------------------------------------------------------------
    # Advanced: Manipulation Detection
    # ----------------------------------------------------------------
    MANIPULATION_VOLUME_SPIKE: float = float(os.getenv("MANIPULATION_VOLUME_SPIKE", "3.0"))
    MANIPULATION_PRICE_REVERSAL: float = float(os.getenv("MANIPULATION_PRICE_REVERSAL", "0.02"))

    # ----------------------------------------------------------------
    # Advanced: Learning Engine
    # ----------------------------------------------------------------
    LEARNING_WEIGHT_ADJUSTMENT: float = float(os.getenv("LEARNING_WEIGHT_ADJUSTMENT", "0.05"))

    # ----------------------------------------------------------------
    # Propiedades derivadas
    # ----------------------------------------------------------------
    @property
    def is_paper_mode(self) -> bool:
        """Retorna True si el bot está en modo simulación (paper trading)."""
        return self.TRADING_MODE.lower() == "paper"

    @property
    def is_live_mode(self) -> bool:
        """Retorna True si el bot está en modo producción (trading real)."""
        return self.TRADING_MODE.lower() == "live"

    @property
    def db_full_path(self) -> Path:
        """Retorna la ruta absoluta de la base de datos."""
        return BASE_DIR / self.DB_PATH

    @property
    def whale_thresholds(self) -> dict:
        """Retorna los umbrales de detección de whales por símbolo."""
        return {
            "BTCUSDT": self.WHALE_THRESHOLD_BTC,
            "ETHUSDT": self.WHALE_THRESHOLD_ETH,
        }

    def __repr__(self) -> str:
        mode = "🟡 PAPER" if self.is_paper_mode else "🔴 LIVE"
        return (
            f"Settings(mode={mode}, symbols={self.SYMBOLS}, "
            f"capital={self.INITIAL_CAPITAL}, ai={self.AI_PROVIDER}/{self.AI_MODEL})"
        )


# Instancia global de configuración
settings = Settings()
