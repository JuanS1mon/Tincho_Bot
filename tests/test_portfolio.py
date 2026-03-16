"""
tests/test_portfolio.py
=======================
Pruebas del seguimiento de portafolio y posiciones.
No requiere conexión a Binance ni MongoDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.portfolio_tool import PortfolioTool, Position


@pytest.fixture
def portfolio():
    """Portfolio nuevo con capital inicial de 1000 USDT para cada test."""
    p = PortfolioTool()
    p.capital = 1000.0
    p.initial_capital = 1000.0
    p.positions = {}
    p.trade_history = []
    p.total_trades = 0
    p.winning_trades = 0
    return p


def _pos(symbol="BTCUSDT", direction="LONG", price=50000.0, qty=0.01, capital=100.0):
    return Position(
        symbol=symbol,
        direction=direction,
        entry_price=price,
        quantity=qty,
        capital_used=capital,
        stop_loss=price * 0.98,
        take_profit=price * 1.06,
    )


class TestPortfolioCapital:

    def test_capital_inicial(self, portfolio):
        assert portfolio.capital == 1000.0
        assert portfolio.initial_capital == 1000.0

    def test_pnl_inicial_cero(self, portfolio):
        assert portfolio.total_pnl == 0.0

    def test_capital_disponible_sin_posiciones(self, portfolio):
        assert portfolio.available_capital == 1000.0

    def test_capital_disponible_descuenta_posicion(self, portfolio):
        pos = _pos(capital=200.0)
        portfolio.open_position(pos)
        assert portfolio.available_capital == 800.0

    def test_capital_por_simbolo_usa_capital_global_disponible(self, portfolio):
        alloc = portfolio.available_capital_for_symbol("BTCUSDT")
        assert alloc == 1000.0

    def test_capital_global_disponible_descuenta_posiciones_abiertas(self, portfolio):
        pos = _pos("BTCUSDT", capital=100.0)
        portfolio.open_position(pos)
        avail = portfolio.available_capital_for_symbol("ETHUSDT")
        assert avail == 900.0


class TestOpenClosePosition:

    def test_abrir_posicion_registra_correctamente(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 50000.0, 0.01, 100.0)
        portfolio.open_position(pos)
        assert portfolio.has_open_position("BTCUSDT")
        assert portfolio.get_position("BTCUSDT") is pos

    def test_no_hay_posicion_antes_de_abrir(self, portfolio):
        assert not portfolio.has_open_position("BTCUSDT")
        assert portfolio.get_position("BTCUSDT") is None

    def test_cerrar_posicion_ganadora_incrementa_capital(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 50000.0, 0.01, 100.0)
        portfolio.open_position(pos)
        # Exit a 51000 → ganancia = (51000 - 50000) * 0.01 = 10 USDT
        record = portfolio.close_position("BTCUSDT", exit_price=51000.0)
        assert record is not None
        assert abs(record.pnl - 10.0) < 0.01
        assert portfolio.capital > 1000.0
        assert portfolio.winning_trades == 1

    def test_cerrar_posicion_perdedora_reduce_capital(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 50000.0, 0.01, 100.0)
        portfolio.open_position(pos)
        # Exit a 49000 → pérdida = (49000 - 50000) * 0.01 = -10 USDT
        record = portfolio.close_position("BTCUSDT", exit_price=49000.0)
        assert record is not None
        assert record.pnl < 0
        assert portfolio.capital < 1000.0
        assert portfolio.winning_trades == 0

    def test_cerrar_posicion_short_ganadora(self, portfolio):
        pos = _pos("BTCUSDT", "SHORT", 50000.0, 0.01, 100.0)
        portfolio.open_position(pos)
        # Exit a 49000 → ganancia = (50000 - 49000) * 0.01 = 10 USDT
        record = portfolio.close_position("BTCUSDT", exit_price=49000.0)
        assert record is not None
        assert abs(record.pnl - 10.0) < 0.01

    def test_cerrar_posicion_inexistente_retorna_none(self, portfolio):
        result = portfolio.close_position("XYZUSDT", exit_price=1.0)
        assert result is None

    def test_posicion_eliminada_tras_cerrar(self, portfolio):
        pos = _pos()
        portfolio.open_position(pos)
        portfolio.close_position("BTCUSDT", exit_price=50000.0)
        assert not portfolio.has_open_position("BTCUSDT")


class TestWinRate:

    def test_winrate_sin_trades_es_cero(self, portfolio):
        assert portfolio.win_rate == 0.0

    def test_winrate_con_un_ganador(self, portfolio):
        portfolio.total_trades = 1
        portfolio.winning_trades = 1
        assert portfolio.win_rate == 1.0

    def test_winrate_50_pct(self, portfolio):
        portfolio.total_trades = 4
        portfolio.winning_trades = 2
        assert portfolio.win_rate == 0.5

    def test_historial_se_acumula(self, portfolio):
        for i in range(3):
            pos = _pos("BTCUSDT", price=100.0, qty=1.0, capital=100.0)
            portfolio.open_position(pos)
            portfolio.close_position("BTCUSDT", exit_price=101.0)
        assert portfolio.total_trades == 3
        assert len(portfolio.trade_history) == 3


class TestGetStateDict:

    def test_state_dict_tiene_claves_requeridas(self, portfolio):
        state = portfolio.get_state_dict()
        for key in ["capital", "available_capital", "initial_capital",
                    "total_pnl", "total_trades", "win_rate", "positions"]:
            assert key in state

    def test_state_dict_capital_correcto(self, portfolio):
        state = portfolio.get_state_dict()
        assert state["capital"] == 1000.0
        assert state["initial_capital"] == 1000.0
        assert state["total_pnl"] == 0.0


class TestProfitLock:

    def test_profit_lock_no_dispara_sin_pico_positivo(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 100.0, 1.0, 100.0)
        portfolio.open_position(pos)
        # Precio por debajo de entrada: no hay pico de ganancia
        hit, pnl_now, peak_pnl, floor_pnl = portfolio.profit_lock_state("BTCUSDT", 99.0)
        assert hit is False
        assert pnl_now < 0
        assert peak_pnl == 0.0
        assert floor_pnl == 0.0

    def test_profit_lock_dispara_si_retrocede_mas_de_15_del_pico(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 100.0, 1.0, 100.0)
        portfolio.open_position(pos)

        # Pico de +10 USDT
        portfolio.profit_lock_state("BTCUSDT", 110.0)

        # Piso permitido = 8.5 USDT (retroceso del 15% del pico)
        hit, pnl_now, peak_pnl, floor_pnl = portfolio.profit_lock_state("BTCUSDT", 108.0)
        assert hit is True
        assert peak_pnl == pytest.approx(10.0, abs=1e-6)
        assert floor_pnl == pytest.approx(8.5, abs=1e-6)
        assert pnl_now == pytest.approx(8.0, abs=1e-6)

    def test_profit_lock_no_dispara_si_retroceso_esta_dentro_del_15(self, portfolio):
        pos = _pos("BTCUSDT", "LONG", 100.0, 1.0, 100.0)
        portfolio.open_position(pos)

        # Pico +10 USDT
        portfolio.profit_lock_state("BTCUSDT", 110.0)

        # +9 USDT sigue encima del piso (+8.5)
        hit, pnl_now, peak_pnl, floor_pnl = portfolio.profit_lock_state("BTCUSDT", 109.0)
        assert hit is False
        assert peak_pnl == pytest.approx(10.0, abs=1e-6)
        assert floor_pnl == pytest.approx(8.5, abs=1e-6)
        assert pnl_now == pytest.approx(9.0, abs=1e-6)
