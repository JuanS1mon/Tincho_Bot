"""
Domain Entity - Market Data
============================
Encapsula datos de mercado (candlesticks OHLCV) por símbolo e intervalo.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from config.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CandlestickData:
    """Datos de una vela individual."""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class MarketData:
    """
    Contenedor de datos de mercado para un símbolo.
    Almacena candlesticks OHLCV para múltiples intervalos.
    """
    symbol: str
    klines: Dict[str, pd.DataFrame] = field(default_factory=dict)
    current_price: float = 0.0
    last_update: Optional[datetime] = None

    def set_klines(self, interval: str, df: pd.DataFrame) -> None:
        """
        Almacena un DataFrame de klines para un intervalo dado.
        
        El DataFrame debe tener columnas: 
        ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        """
        self.klines[interval] = df
        self.last_update = datetime.utcnow()
        logger.debug(
            f"Klines actualizados: {self.symbol} [{interval}] - "
            f"{len(df)} velas cargadas"
        )

    def get_klines(self, interval: str) -> Optional[pd.DataFrame]:
        """Obtiene el DataFrame de klines para un intervalo."""
        return self.klines.get(interval)

    def get_latest_close(self, interval: str = "1h") -> Optional[float]:
        """Obtiene el último precio de cierre para un intervalo."""
        df = self.get_klines(interval)
        if df is not None and len(df) > 0:
            return float(df["close"].iloc[-1])
        return None

    def get_closes(self, interval: str) -> Optional[pd.Series]:
        """Obtiene la serie de precios de cierre para un intervalo."""
        df = self.get_klines(interval)
        if df is not None:
            return df["close"].astype(float)
        return None

    def get_volumes(self, interval: str) -> Optional[pd.Series]:
        """Obtiene la serie de volúmenes para un intervalo."""
        df = self.get_klines(interval)
        if df is not None:
            return df["volume"].astype(float)
        return None

    def to_summary(self) -> dict:
        """Genera un resumen del estado de datos cargados."""
        return {
            "symbol": self.symbol,
            "current_price": self.current_price,
            "intervals_loaded": list(self.klines.keys()),
            "candles_per_interval": {
                interval: len(df) for interval, df in self.klines.items()
            },
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


@dataclass 
class MarketSnapshot:
    """
    Resumen analítico del estado del mercado para un símbolo.
    Generado por MarketAnalyzer.
    """
    symbol: str
    price: float
    trend: str  # bullish, bearish, sideways
    momentum: str  # strong_bullish, bullish, neutral, bearish, strong_bearish
    volatility: float  # porcentaje
    volatility_state: str  # low, medium, high
    volume_trend: str  # increasing, decreasing, stable
    rsi: float
    macd_signal: str  # bullish, bearish, neutral
    sma_20: float
    sma_50: float
    ema_20: float
    market_state: str  # bullish, bearish, sideways, high_volatility
    timestamp: Optional[datetime] = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Serializa el snapshot para almacenamiento o envío a IA."""
        return {
            "symbol": self.symbol,
            "price": round(self.price, 2),
            "trend": self.trend,
            "momentum": self.momentum,
            "volatility": f"{self.volatility:.2f}%",
            "volatility_state": self.volatility_state,
            "volume_trend": self.volume_trend,
            "rsi": round(self.rsi, 2),
            "macd_signal": self.macd_signal,
            "sma_20": round(self.sma_20, 2),
            "sma_50": round(self.sma_50, 2),
            "ema_20": round(self.ema_20, 2),
            "market_state": self.market_state,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
