"""
config/settings.py
==================
Carga y valida todas las variables de entorno usando pydantic-settings.
Instancia singleton: from config.settings import settings
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Binance ───────────────────────────────────────────────────────────────
    binance_api_key: str = ""
    binance_secret_key: str = ""
    binance_testnet: bool = True

    # ── IA ────────────────────────────────────────────────────────────────────
    ai_provider: str = "deepseek"
    ai_model: str = "deepseek-chat"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com"

    # ── Trading ───────────────────────────────────────────────────────────────
    initial_capital: float = 100.0
    # SYMBOLS se guarda como str CSV y se expone como List[str] via property
    symbols_csv: str = "BTCUSDT,ETHUSDT"
    leverage: int = 3
    max_capital_per_trade: float = 0.30
    risk_per_trade: float = 0.01
    stop_loss: float = 0.02
    take_profit: float = 0.06
    timeframe: str = "15m"
    analysis_interval_seconds: int = 900
    min_winrate: float = 0.45

    # ── MongoDB ───────────────────────────────────────────────────────────────
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "tincho_bot"

    # ── API HTTP ──────────────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def symbols(self) -> List[str]:
        """Parsea SYMBOLS (o SYMBOLS_CSV) desde string CSV."""
        return [s.strip().upper() for s in self.symbols_csv.split(",") if s.strip()]

    @property
    def base_dir(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def logs_dir(self) -> Path:
        p = self.base_dir / "logs"
        p.mkdir(exist_ok=True)
        return p

    @property
    def data_dir(self) -> Path:
        p = self.base_dir / "data"
        p.mkdir(exist_ok=True)
        return p


# Singleton global
settings = Settings()
