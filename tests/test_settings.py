"""
tests/test_settings.py
=======================
Pruebas de carga de configuración desde .env.
No requiere conexión a Binance ni MongoDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config.settings import Settings


class TestSettings:

    def test_settings_carga_sin_error(self):
        """Settings debe instanciarse sin lanzar excepciones."""
        s = Settings(_env_file=".env")
        assert s is not None

    def test_symbols_csv_a_lista(self):
        s = Settings(symbols_csv="BTCUSDT,ETHUSDT", _env_file=None)
        assert s.symbols == ["BTCUSDT", "ETHUSDT"]

    def test_symbols_csv_trimmea_espacios(self):
        s = Settings(symbols_csv=" BTCUSDT , ETHUSDT ", _env_file=None)
        assert "BTCUSDT" in s.symbols
        assert "ETHUSDT" in s.symbols

    def test_symbols_csv_un_solo_simbolo(self):
        s = Settings(symbols_csv="BTCUSDT", _env_file=None)
        assert s.symbols == ["BTCUSDT"]

    def test_symbols_upcase(self):
        s = Settings(symbols_csv="btcusdt,ethusdt", _env_file=None)
        assert s.symbols == ["BTCUSDT", "ETHUSDT"]

    def test_valores_por_defecto_razonables(self):
        s = Settings(_env_file=None)
        assert s.leverage >= 1
        assert 0 < s.max_capital_per_trade <= 1.0
        assert 0 < s.stop_loss <= 0.5
        assert 0 < s.take_profit <= 1.0
        assert s.take_profit > s.stop_loss  # TP siempre mayor que SL

    def test_initial_capital_positivo(self):
        s = Settings(_env_file=None)
        assert s.initial_capital > 0

    def test_timeframe_valido(self):
        s = Settings(_env_file=None)
        valid_tfs = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}
        assert s.timeframe in valid_tfs

    def test_api_port_valido(self):
        s = Settings(_env_file=None)
        assert 1024 <= s.api_port <= 65535

    def test_mongo_uri_tiene_esquema(self):
        s = Settings(_env_file=None)
        assert s.mongo_uri.startswith("mongodb://") or s.mongo_uri.startswith("mongodb+srv://")

    def test_take_profit_mayor_que_stop_loss_desde_env(self):
        """El TP del .env puede ser > SL o 0 cuando está deshabilitado."""
        from config.settings import settings
        assert settings.take_profit == 0 or settings.take_profit > settings.stop_loss, (
            f"TAKE_PROFIT ({settings.take_profit}) debe ser 0 (OFF) o mayor que STOP_LOSS ({settings.stop_loss})"
        )
