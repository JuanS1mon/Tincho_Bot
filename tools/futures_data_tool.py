"""
tools/futures_data_tool.py
===========================
Agrega datos avanzados de futuros por símbolo:
  - Open Interest (actual + histórico)
  - Funding Rate
  - Liquidaciones
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List

from exchange.market_fetcher import market_fetcher
from analysis.open_interest_analyzer import open_interest_analyzer, OIAnalysis
from analysis.liquidation_analyzer import liquidation_analyzer, LiquidationAnalysis
from config.logger import trading_logger as logger, error_logger

CACHE_TTL: int = 120  # 2 minutos


@dataclass
class FuturesSnapshot:
    symbol: str
    oi_analysis: OIAnalysis
    liquidation_analysis: LiquidationAnalysis
    funding_rate: float
    oi_history: List[dict]
    raw_liquidations: List[dict]
    timestamp: float = field(default_factory=time.time)

    def is_fresh(self, ttl: int = CACHE_TTL) -> bool:
        return (time.time() - self.timestamp) < ttl


class FuturesDataTool:
    """Obtiene y analiza datos avanzados de futuros."""

    def __init__(self) -> None:
        self._cache: dict = {}

    def get(self, symbol: str, current_price: float, prev_price: float,
            force_refresh: bool = False) -> FuturesSnapshot:
        """
        Retorna snapshot de datos de futuros para el símbolo.
        current_price y prev_price se usan para correlacionar con OI.
        """
        cached = self._cache.get(symbol)
        if cached and cached.is_fresh() and not force_refresh:
            return cached

        try:
            logger.debug("Fetching datos de futuros para %s...", symbol)

            oi_history = market_fetcher.get_open_interest_history(symbol, period="15m", limit=20)
            funding_data = market_fetcher.get_funding_rate(symbol)
            liquidations = market_fetcher.get_liquidations(symbol, limit=50)

            oi_analysis = open_interest_analyzer.analyze(oi_history, current_price, prev_price)
            liq_analysis = liquidation_analyzer.analyze(liquidations)

            snapshot = FuturesSnapshot(
                symbol=symbol,
                oi_analysis=oi_analysis,
                liquidation_analysis=liq_analysis,
                funding_rate=funding_data.get("funding_rate", 0.0),
                oi_history=oi_history,
                raw_liquidations=liquidations,
            )
            self._cache[symbol] = snapshot
            logger.debug(
                "Futuros %s: OI=%s, funding=%.4f%%",
                symbol, oi_analysis.trend, funding_data.get("funding_rate", 0) * 100
            )
            return snapshot

        except Exception as exc:
            error_logger.error("FuturesDataTool.get(%s) error: %s", symbol, exc)
            # Retornar snapshot vacío para no bloquear el ciclo del agente
            from analysis.open_interest_analyzer import OIAnalysis
            from analysis.liquidation_analyzer import LiquidationAnalysis
            return FuturesSnapshot(
                symbol=symbol,
                oi_analysis=OIAnalysis(0, 0, "STABLE", "NEUTRAL", "Error al obtener OI"),
                liquidation_analysis=LiquidationAnalysis(0, 0, 0, 0, "BALANCED", "NEUTRAL", "Error"),
                funding_rate=0.0,
                oi_history=[],
                raw_liquidations=[],
            )


# Instancia global
futures_data_tool = FuturesDataTool()
