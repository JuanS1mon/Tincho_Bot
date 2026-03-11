"""
Infrastructure - Binance Client
=================================
Wrapper profesional sobre python-binance con:
  - Soporte testnet
  - Reconexión automática (retry exponencial)
  - Obtención de klines, balance, precios, order book, trades
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceRequestException

from config.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

# URLs de Binance Testnet
TESTNET_API_URL = "https://testnet.binance.vision/api"
TESTNET_WS_URL = "wss://testnet.binance.vision/ws"


class BinanceClientWrapper:
    """
    Cliente de Binance con reconexión automática y soporte testnet.
    Encapsula todas las operaciones de lectura con la API de Binance.
    """

    def __init__(self):
        self.client: Optional[Client] = None
        self._max_retries = 3
        self._retry_delay = 2  # segundos base para retry exponencial
        self._connect()

    def _connect(self) -> None:
        """Establece conexión con Binance (testnet o producción)."""
        try:
            if settings.BINANCE_TESTNET:
                self.client = Client(
                    api_key=settings.BINANCE_API_KEY,
                    api_secret=settings.BINANCE_SECRET_KEY,
                    testnet=True,
                )
                logger.info("🔗 Conectado a Binance TESTNET")
            else:
                self.client = Client(
                    api_key=settings.BINANCE_API_KEY,
                    api_secret=settings.BINANCE_SECRET_KEY,
                )
                logger.info("🔗 Conectado a Binance PRODUCCIÓN")
        except Exception as e:
            logger.error(f"Error conectando a Binance: {e}")
            raise

    def _retry_operation(self, operation, *args, **kwargs):
        """
        Ejecuta una operación con retry exponencial.
        Reconecta automáticamente si la conexión se pierde.
        """
        for attempt in range(1, self._max_retries + 1):
            try:
                return operation(*args, **kwargs)
            except (BinanceAPIException, BinanceRequestException) as e:
                logger.warning(
                    f"Binance API error (intento {attempt}/{self._max_retries}): {e}"
                )
                if attempt < self._max_retries:
                    delay = self._retry_delay * (2 ** (attempt - 1))
                    logger.info(f"Reintentando en {delay}s...")
                    time.sleep(delay)
                    # Intentar reconexión
                    try:
                        self._connect()
                    except Exception:
                        pass
                else:
                    logger.error(f"Operación fallida después de {self._max_retries} intentos")
                    raise
            except Exception as e:
                logger.error(f"Error inesperado en operación Binance: {e}")
                raise

    def get_klines(
        self,
        symbol: str,
        interval: str,
        days: int = 30,
    ) -> pd.DataFrame:
        """
        Obtiene datos de candlesticks (klines) de Binance.
        
        Args:
            symbol: Par de trading (ej: "BTCUSDT").
            interval: Intervalo ("1h", "4h", "1d").
            days: Cantidad de días hacia atrás.
            
        Returns:
            DataFrame con columnas: timestamp, open, high, low, close, volume.
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        start_str = start_time.strftime("%d %b %Y")

        raw_klines = self._retry_operation(
            self.client.get_historical_klines,
            symbol,
            interval,
            start_str,
        )

        if not raw_klines:
            logger.warning(f"Sin datos de klines para {symbol} [{interval}]")
            return pd.DataFrame()

        # Parsear a DataFrame
        df = pd.DataFrame(raw_klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
        ])

        # Convertir tipos
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)

        # Mantener solo columnas necesarias
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]

        logger.debug(f"Klines obtenidos: {symbol} [{interval}] - {len(df)} velas")
        return df

    def get_balance(self, asset: str = "USDT") -> float:
        """
        Obtiene el balance libre de un activo.
        
        Args:
            asset: Activo a consultar (default "USDT").
            
        Returns:
            Balance disponible (free) como float.
        """
        try:
            balance_info = self._retry_operation(
                self.client.get_asset_balance, asset=asset
            )
            if balance_info:
                free = float(balance_info.get("free", 0))
                logger.debug(f"Balance {asset}: {free}")
                return free
            return 0.0
        except Exception as e:
            logger.error(f"Error obteniendo balance de {asset}: {e}")
            return 0.0

    def get_all_balances(self) -> Dict[str, float]:
        """
        Obtiene todos los balances no-cero de la cuenta.
        
        Returns:
            Diccionario {asset: balance_free}.
        """
        try:
            account = self._retry_operation(self.client.get_account)
            balances = {}
            for b in account.get("balances", []):
                free = float(b["free"])
                if free > 0:
                    balances[b["asset"]] = free
            return balances
        except Exception as e:
            logger.error(f"Error obteniendo balances: {e}")
            return {}

    def get_ticker_price(self, symbol: str) -> float:
        """
        Obtiene el precio actual de un símbolo.
        
        Args:
            symbol: Par de trading (ej: "BTCUSDT").
            
        Returns:
            Precio actual como float.
        """
        try:
            ticker = self._retry_operation(
                self.client.get_symbol_ticker, symbol=symbol
            )
            price = float(ticker.get("price", 0))
            logger.debug(f"Precio {symbol}: {price}")
            return price
        except Exception as e:
            logger.error(f"Error obteniendo precio de {symbol}: {e}")
            return 0.0

    def get_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Obtiene precios actuales de múltiples símbolos.
        
        Returns:
            Diccionario {symbol: price}.
        """
        prices = {}
        for symbol in symbols:
            prices[symbol] = self.get_ticker_price(symbol)
        return prices

    def get_order_book(self, symbol: str, limit: int = 100) -> dict:
        """
        Obtiene el order book (profundidad de mercado).
        
        Args:
            symbol: Par de trading.
            limit: Cantidad de niveles (default 100).
            
        Returns:
            Dict con 'bids' y 'asks', cada uno lista de [price, quantity].
        """
        try:
            depth = self._retry_operation(
                self.client.get_order_book, symbol=symbol, limit=limit
            )
            return {
                "bids": [[float(b[0]), float(b[1])] for b in depth.get("bids", [])],
                "asks": [[float(a[0]), float(a[1])] for a in depth.get("asks", [])],
                "lastUpdateId": depth.get("lastUpdateId"),
            }
        except Exception as e:
            logger.error(f"Error obteniendo order book de {symbol}: {e}")
            return {"bids": [], "asks": []}

    def get_recent_trades(self, symbol: str, limit: int = 500) -> List[dict]:
        """
        Obtiene los trades más recientes.
        
        Args:
            symbol: Par de trading.
            limit: Cantidad de trades (max 1000).
            
        Returns:
            Lista de trades con price, qty, time, isBuyerMaker.
        """
        try:
            trades = self._retry_operation(
                self.client.get_recent_trades, symbol=symbol, limit=limit
            )
            return [
                {
                    "price": float(t["price"]),
                    "quantity": float(t["qty"]),
                    "time": datetime.fromtimestamp(t["time"] / 1000),
                    "is_buyer_maker": t["isBuyerMaker"],
                }
                for t in trades
            ]
        except Exception as e:
            logger.error(f"Error obteniendo trades de {symbol}: {e}")
            return []

    def get_exchange_info(self, symbol: str) -> Optional[dict]:
        """Obtiene información del par de trading (filtros, decimales, etc)."""
        try:
            info = self._retry_operation(self.client.get_exchange_info)
            for s in info.get("symbols", []):
                if s["symbol"] == symbol:
                    return s
            return None
        except Exception as e:
            logger.error(f"Error obteniendo exchange info: {e}")
            return None
