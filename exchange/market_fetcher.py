"""
binance/market_fetcher.py
=========================
Obtiene datos de mercado desde la API de Binance Futures:
  - Velas OHLCV (klines)
  - Ticker 24h (precio, volumen)
  - Order book depth
  - Open Interest
  - Funding rate
  - Liquidaciones (forced orders)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from binance.client import Client

from exchange.futures_client import futures_client
from config.settings import settings
from config.logger import trading_logger as logger, error_logger

# Mapa de timeframes de Binance
_TF_MAP: Dict[str, str] = {
    "1m": Client.KLINE_INTERVAL_1MINUTE,
    "5m": Client.KLINE_INTERVAL_5MINUTE,
    "15m": Client.KLINE_INTERVAL_15MINUTE,
    "30m": Client.KLINE_INTERVAL_30MINUTE,
    "1h": Client.KLINE_INTERVAL_1HOUR,
    "4h": Client.KLINE_INTERVAL_4HOUR,
    "1d": Client.KLINE_INTERVAL_1DAY,
}


class MarketFetcher:
    """Obtiene y transforma datos de mercado de Binance Futures."""

    def __init__(self) -> None:
        self._client = futures_client

    # ── Klines ────────────────────────────────────────────────────────────────

    def get_klines(
        self,
        symbol: str,
        interval: Optional[str] = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """
        Retorna DataFrame OHLCV con columnas:
        open_time, open, high, low, close, volume
        """
        tf = _TF_MAP.get(interval or settings.timeframe, Client.KLINE_INTERVAL_15MINUTE)
        try:
            raw = self._client.safe_call(
                self._client.client.futures_klines,
                symbol=symbol,
                interval=tf,
                limit=limit,
            )
            df = pd.DataFrame(raw, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_asset_volume", "number_of_trades",
                "taker_buy_base", "taker_buy_quote", "ignore",
            ])
            numeric_cols = ["open", "high", "low", "close", "volume"]
            df[numeric_cols] = df[numeric_cols].astype(float)
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            return df[["open_time", "open", "high", "low", "close", "volume"]]
        except Exception as exc:
            error_logger.error("get_klines(%s) error: %s", symbol, exc)
            raise

    # ── Ticker ────────────────────────────────────────────────────────────────

    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Precio actual, volumen 24h y variación porcentual."""
        try:
            data = self._client.safe_call(
                self._client.client.futures_ticker,
                symbol=symbol,
            )
            return {
                "symbol": symbol,
                "price": float(data["lastPrice"]),
                "volume_24h": float(data["volume"]),
                "price_change_pct": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            error_logger.error("get_ticker(%s) error: %s", symbol, exc)
            raise

    # ── Order Book ────────────────────────────────────────────────────────────

    def get_orderbook(self, symbol: str, limit: int = 20) -> Dict[str, Any]:
        """Retorna las mejores N bids y asks del libro de órdenes."""
        try:
            data = self._client.safe_call(
                self._client.client.futures_order_book,
                symbol=symbol,
                limit=limit,
            )
            bids = [[float(p), float(q)] for p, q in data["bids"]]
            asks = [[float(p), float(q)] for p, q in data["asks"]]
            return {"symbol": symbol, "bids": bids, "asks": asks}
        except Exception as exc:
            error_logger.error("get_orderbook(%s) error: %s", symbol, exc)
            raise

    # ── Open Interest ─────────────────────────────────────────────────────────

    def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """Open interest actual del contrato perpetuo."""
        try:
            data = self._client.safe_call(
                self._client.client.futures_open_interest,
                symbol=symbol,
            )
            return {
                "symbol": symbol,
                "open_interest": float(data["openInterest"]),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as exc:
            error_logger.error("get_open_interest(%s) error: %s", symbol, exc)
            raise

    def get_open_interest_history(self, symbol: str, period: str = "15m", limit: int = 50) -> List[Dict]:
        """Historial de open interest para detectar tendencia."""
        try:
            raw = self._client.safe_call(
                self._client.client.futures_open_interest_hist,
                symbol=symbol,
                period=period,
                limit=limit,
            )
            return [
                {
                    "timestamp": r["timestamp"],
                    "open_interest": float(r["sumOpenInterest"]),
                    "open_interest_value": float(r["sumOpenInterestValue"]),
                }
                for r in raw
            ]
        except Exception as exc:
            error_logger.error("get_open_interest_history(%s) error: %s", symbol, exc)
            return []

    # ── Funding Rate ──────────────────────────────────────────────────────────

    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """Funding rate actual."""
        try:
            data = self._client.safe_call(
                self._client.client.futures_funding_rate,
                symbol=symbol,
                limit=1,
            )
            if data:
                return {
                    "symbol": symbol,
                    "funding_rate": float(data[0]["fundingRate"]),
                    "funding_time": data[0]["fundingTime"],
                }
            return {"symbol": symbol, "funding_rate": 0.0, "funding_time": None}
        except Exception as exc:
            error_logger.error("get_funding_rate(%s) error: %s", symbol, exc)
            return {"symbol": symbol, "funding_rate": 0.0, "funding_time": None}

    # ── Liquidaciones ─────────────────────────────────────────────────────────

    def get_liquidations(self, symbol: str, limit: int = 50) -> List[Dict]:
        """
        Fetch forced liquidation orders (allForceOrders).
        Retorna lista con side, price, qty, time.
        """
        try:
            raw = self._client.safe_call(
                self._client.client.futures_coin_liquidation_orders,
                symbol=symbol,
                limit=limit,
            )
        except Exception:
            # Fallback: endpoint alternativo para algunos pares
            try:
                raw = self._client.safe_call(
                    self._client.client.futures_liquidation_orders,
                    symbol=symbol,
                    limit=limit,
                )
            except Exception as exc:
                error_logger.error("get_liquidations(%s) error: %s", symbol, exc)
                return []

        result = []
        for order in raw:
            result.append({
                "symbol": symbol,
                "side": order.get("side"),
                "price": float(order.get("price", 0)),
                "qty": float(order.get("origQty", 0)),
                "time": order.get("time"),
            })
        return result


# Instancia global
market_fetcher = MarketFetcher()
