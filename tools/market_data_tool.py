"""
tools/market_data_tool.py
=========================
Agrega y cachea datos de mercado por símbolo:
  - Klines OHLCV
  - Ticker (precio actual)
  - Indicadores técnicos calculados
  - Order book

El caché evita llamadas repetidas durante el mismo ciclo de análisis.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import pandas as pd

from exchange.market_fetcher import market_fetcher, MarketFetcher
from tools.indicator_tool import indicator_tool, Indicators
from config.logger import trading_logger as logger, error_logger


# Tiempo mínimo entre refetches (segundos) — evita rate limiting
CACHE_TTL: int = 60


@dataclass
class MarketSnapshot:
    symbol: str
    df: pd.DataFrame
    ticker: dict
    indicators: Optional[Indicators]
    orderbook: dict
    timestamp: float = field(default_factory=time.time)

    def is_fresh(self, ttl: int = CACHE_TTL) -> bool:
        return (time.time() - self.timestamp) < ttl


class MarketDataTool:
    """Fetcher de datos de mercado con caché por símbolo."""

    def __init__(self, fetcher: MarketFetcher = market_fetcher) -> None:
        self._fetcher = fetcher
        self._cache: Dict[str, MarketSnapshot] = {}

    def get(self, symbol: str, force_refresh: bool = False) -> MarketSnapshot:
        """
        Retorna datos frescos de mercado para el símbolo.
        Usa caché si los datos tienen menos de CACHE_TTL segundos.
        """
        cached = self._cache.get(symbol)
        if cached and cached.is_fresh() and not force_refresh:
            return cached

        try:
            logger.debug("Fetching datos de mercado para %s...", symbol)
            df = self._fetcher.get_klines(symbol, limit=200)
            ticker = self._fetcher.get_ticker(symbol)
            orderbook = self._fetcher.get_orderbook(symbol, limit=20)
            indicators = indicator_tool.calculate(df)

            snapshot = MarketSnapshot(
                symbol=symbol,
                df=df,
                ticker=ticker,
                indicators=indicators,
                orderbook=orderbook,
            )
            self._cache[symbol] = snapshot
            logger.debug("Snapshot actualizado para %s @ %.2f", symbol, ticker["price"])
            return snapshot

        except Exception as exc:
            error_logger.error("MarketDataTool.get(%s) error: %s", symbol, exc)
            raise

    def invalidate(self, symbol: Optional[str] = None) -> None:
        """Invalida el caché de un símbolo o de todos si symbol=None."""
        if symbol:
            self._cache.pop(symbol, None)
        else:
            self._cache.clear()


# Instancia global
market_data_tool = MarketDataTool()
