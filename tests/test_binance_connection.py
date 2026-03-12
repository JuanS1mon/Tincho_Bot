"""
tests/test_binance_connection.py
=================================
Prueba la conectividad real con Binance Testnet.
Requiere claves en .env y conexión a internet.

Ejecutar solo para verificar antes de lanzar el bot:
  pytest tests/test_binance_connection.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config.settings import settings


# Saltar si no hay claves configuradas
pytestmark = pytest.mark.skipif(
    not settings.binance_api_key or not settings.binance_secret_key,
    reason="Claves Binance no configuradas en .env"
)


class TestBinanceConnection:

    def test_ping_binance(self):
        """Verifica que la API de Binance responde."""
        from exchange.futures_client import futures_client
        client = futures_client.client
        result = client.ping()
        # ping() retorna {} en éxito
        assert result is not None

    def test_obtener_precio_btc(self):
        """Verifica que se puede obtener el precio de BTCUSDT."""
        from exchange.market_fetcher import market_fetcher
        ticker = market_fetcher.get_ticker("BTCUSDT")
        assert ticker is not None
        assert "price" in ticker
        assert ticker["price"] > 0, "Precio de BTC debe ser mayor a 0"

    def test_obtener_precio_eth(self):
        """Verifica que se puede obtener el precio de ETHUSDT."""
        from exchange.market_fetcher import market_fetcher
        ticker = market_fetcher.get_ticker("ETHUSDT")
        assert ticker is not None
        assert ticker["price"] > 0

    def test_obtener_klines_btc(self):
        """Verifica que se pueden obtener velas OHLCV de BTCUSDT."""
        from exchange.market_fetcher import market_fetcher
        import pandas as pd
        df = market_fetcher.get_klines("BTCUSDT", interval="15m", limit=60)
        assert df is not None
        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 50, f"Se esperaban ≥50 velas, se recibieron {len(df)}"
        for col in ["open", "high", "low", "close", "volume"]:
            assert col in df.columns, f"Falta columna {col}"

    def test_calcular_indicadores_con_datos_reales(self):
        """Verifica que los indicadores se calculan correctamente con datos reales."""
        from exchange.market_fetcher import market_fetcher
        from tools.indicator_tool import indicator_tool
        df = market_fetcher.get_klines("BTCUSDT", interval="15m", limit=100)
        ind = indicator_tool.calculate(df)
        assert ind is not None
        assert ind.price > 0
        assert 0 <= ind.rsi <= 100
        assert ind.sma20 > 0
        assert ind.sma50 > 0

    def test_saldo_usdt_futures(self):
        """Verifica que se puede leer el saldo de la cuenta Futures."""
        from exchange.market_fetcher import market_fetcher
        balance = market_fetcher.get_usdt_balance()
        # Puede ser None si no hay permisos, o un float ≥ 0
        assert balance is None or balance >= 0, f"Balance inválido: {balance}"
        if balance is not None:
            print(f"\n  ✓ Saldo USDT en Futures: {balance:.4f} USDT")

    def test_funding_rate_btc(self):
        """Verifica que se puede obtener la tasa de financiamiento."""
        from exchange.market_fetcher import market_fetcher
        funding = market_fetcher.get_funding_rate("BTCUSDT")
        assert funding is not None
        assert "funding_rate" in funding

    def test_open_interest_btc(self):
        """Verifica que se puede obtener el Open Interest de BTCUSDT."""
        from exchange.market_fetcher import market_fetcher
        oi = market_fetcher.get_open_interest("BTCUSDT")
        assert oi is not None
