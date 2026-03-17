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

from datetime import datetime, timezone
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
        Nota: en testnet este endpoint no está disponible (retorna -2015).
        """
        # En testnet el endpoint de liquidaciones no existe — omitir silenciosamente
        if settings.binance_testnet:
            return []

        from binance.exceptions import BinanceAPIException as _BinExc
        try:
            raw = self._client.client.futures_coin_liquidation_orders(
                symbol=symbol, limit=limit
            )
        except _BinExc as exc:
            if exc.code == -2015:
                logger.debug("get_liquidations(%s): sin permisos (dato opcional, ignorado)", symbol)
                return []
            # Fallback: endpoint alternativo para algunos pares
            try:
                raw = self._client.client.futures_liquidation_orders(
                    symbol=symbol, limit=limit
                )
            except _BinExc as exc2:
                if exc2.code != -2015:
                    error_logger.error("get_liquidations(%s) error: %s", symbol, exc2)
                return []
        except Exception as exc:
            error_logger.error("get_liquidations(%s) error inesperado: %s", symbol, exc)
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

    # ── Balance de cuenta ─────────────────────────────────────────────────────

    def get_usdt_available_balance(self) -> Optional[float]:
        """
        Retorna el availableBalance real de USDT-M Futures para abrir nuevas posiciones.
        Prioriza:
          - availableBalance
          - withdrawAvailable
        """
        from binance.exceptions import BinanceAPIException as _BinExc

        def _extract_available(assets: List[Dict[str, Any]]) -> Optional[float]:
            for asset in assets:
                if asset.get("asset") != "USDT":
                    continue
                available = float(
                    asset.get("availableBalance", asset.get("withdrawAvailable", 0)) or 0
                )
                logger.info("Available Binance Futures (USDT): %.4f", available)
                return available
            return None

        try:
            balances = self._client.safe_call(self._client.client.futures_account_balance)
            available = _extract_available(balances)
            if available is not None:
                return available

            account = self._client.safe_call(self._client.client.futures_account)
            assets = account.get("assets", []) if isinstance(account, dict) else []
            available = _extract_available(assets)
            if available is not None:
                return available

            logger.warning(
                "get_usdt_available_balance: no se encontró asset USDT en respuesta de Binance Futures."
            )
        except _BinExc as exc:
            if exc.code == -2015:
                logger.debug(
                    "get_usdt_available_balance: sin permisos (-2015). "
                    "Verificá API key Futures e IP whitelist."
                )
            elif exc.code == -1021:
                logger.warning(
                    "get_usdt_available_balance: timestamp fuera de ventana (-1021)."
                )
            else:
                logger.warning("No se pudo obtener availableBalance de Binance: %s", exc)
        except Exception as exc:
            logger.warning("No se pudo obtener availableBalance de Binance (error inesperado): %s", exc)

        return None

    def get_usdt_balance(self) -> Optional[float]:
        """
                Retorna el saldo total USDT de la cuenta Futures.
                Soporta variantes de campos de Binance en USD-M:
                    - walletBalance / marginBalance / availableBalance
                    - balance / withdrawAvailable / crossUnPnl
        Retorna None si no se puede obtener (error de API, permisos, etc.).
        """
        from binance.exceptions import BinanceAPIException as _BinExc

        def _extract_usdt_balance(assets: List[Dict[str, Any]]) -> Optional[float]:
            for asset in assets:
                if asset.get("asset") == "USDT":
                    # Binance puede devolver distintos nombres de campo según endpoint/cuenta.
                    wallet = float(
                        asset.get("walletBalance", asset.get("balance", 0)) or 0
                    )

                    unrealized = float(
                        asset.get("unrealizedProfit", asset.get("crossUnPnl", 0)) or 0
                    )
                    margin = float(
                        asset.get("marginBalance", wallet + unrealized) or (wallet + unrealized)
                    )

                    available = float(
                        asset.get("availableBalance", asset.get("withdrawAvailable", 0)) or 0
                    )
                    # En algunas cuentas USDⓈ-M la API puede devolver wallet/margin=0
                    # y availableBalance>0. Priorizamos el primer saldo positivo útil.
                    if margin > 0:
                        balance = margin
                        source = "margin"
                    elif wallet > 0:
                        balance = wallet
                        source = "wallet"
                    elif available > 0:
                        balance = available
                        source = "available"
                    else:
                        balance = 0.0
                        source = "none"
                    logger.info(
                        "Saldo Binance Futures (USDT): wallet=%.4f | margin=%.4f | available=%.4f | usando=%s",
                        wallet,
                        margin,
                        available,
                        source,
                    )
                    return balance
            return None

        try:
            balances = self._client.safe_call(self._client.client.futures_account_balance)
            balance = _extract_usdt_balance(balances)
            if balance is not None:
                return balance

            # Fallback para cuentas/endpoints donde balance viene en futures_account().
            account = self._client.safe_call(self._client.client.futures_account)
            assets = account.get("assets", []) if isinstance(account, dict) else []
            balance = _extract_usdt_balance(assets)
            if balance is not None:
                return balance

            logger.warning(
                "get_usdt_balance: no se encontró asset USDT en respuesta de Binance Futures."
            )
        except _BinExc as exc:
            if exc.code == -2015:
                logger.debug(
                    "get_usdt_balance: sin permisos (-2015). "
                    "Verificá en Binance → API Management → habilitá 'Futures' y quitá restricción de IP."
                )
            elif exc.code == -1021:
                logger.warning(
                    "get_usdt_balance: timestamp fuera de ventana (-1021). "
                    "Sincronizá el reloj del sistema y reintentá."
                )
            else:
                logger.warning("No se pudo obtener saldo de Binance: %s", exc)
        except Exception as exc:
            logger.warning("No se pudo obtener saldo de Binance (error inesperado): %s", exc)
        return None


# Instancia global
market_fetcher = MarketFetcher()
