"""
tests/test_risk_tool.py
=======================
Pruebas del cálculo y validación de riesgo por trade.
No requiere conexión a Binance ni MongoDB.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.risk_tool import RiskTool, RiskParams


@pytest.fixture
def risk():
    t = RiskTool()
    # Parámetros fijos para los tests
    t.max_capital_pct = 0.30
    t.risk_per_trade = 0.01
    t.stop_loss_pct = 0.02
    t.take_profit_pct = 0.06
    t.max_leverage = 3
    t.trailing_callback_pct = 1.0
    return t


class TestRiskTool:

    def test_rechaza_capital_cero(self, risk):
        r = risk.validate("LONG", 50000.0, available_capital=0, total_capital=100)
        assert not r.is_valid
        assert "insuficiente" in r.rejection_reason.lower() or r.rejection_reason != ""

    def test_rechaza_capital_negativo(self, risk):
        r = risk.validate("LONG", 50000.0, available_capital=-10, total_capital=100)
        assert not r.is_valid

    def test_rechaza_capital_menor_minimo(self, risk):
        # Capital disponible < 10 USDT → rechazado
        r = risk.validate("LONG", 50000.0, available_capital=5, total_capital=100)
        assert not r.is_valid

    def test_acepta_trade_valido_long(self, risk):
        r = risk.validate("LONG", 50000.0, available_capital=100, total_capital=100)
        assert r.is_valid
        assert r.quantity > 0
        assert r.capital_to_use > 0
        assert r.stop_loss_price < 50000.0  # SL debajo del precio para LONG
        assert r.take_profit_price > 50000.0  # TP arriba del precio para LONG

    def test_acepta_trade_valido_short(self, risk):
        r = risk.validate("SHORT", 50000.0, available_capital=100, total_capital=100)
        assert r.is_valid
        assert r.stop_loss_price > 50000.0    # SL arriba para SHORT
        assert r.take_profit_price < 50000.0  # TP abajo para SHORT

    def test_rr_ratio_minimo_2(self, risk):
        # Con SL=2% y TP=6% → RR = 3.0 → válido
        r = risk.validate("LONG", 100.0, available_capital=100, total_capital=100)
        assert r.is_valid
        assert r.risk_reward_ratio >= 2.0

    def test_capital_usado_no_supera_maximo(self, risk):
        r = risk.validate("LONG", 50000.0, available_capital=1000, total_capital=1000)
        assert r.is_valid
        assert r.capital_to_use <= 1000 * 0.30 + 0.01  # max 30% + tolerancia

    def test_sl_tp_long_correctos(self, risk):
        entry = 100.0
        r = risk.validate("LONG", entry, available_capital=100, total_capital=100)
        assert r.is_valid
        expected_sl = entry * (1 - risk.stop_loss_pct)
        expected_tp = entry * (1 + risk.take_profit_pct)
        assert abs(r.stop_loss_price - expected_sl) < 0.01
        assert abs(r.take_profit_price - expected_tp) < 0.01

    def test_sl_tp_short_correctos(self, risk):
        entry = 100.0
        r = risk.validate("SHORT", entry, available_capital=100, total_capital=100)
        assert r.is_valid
        expected_sl = entry * (1 + risk.stop_loss_pct)
        expected_tp = entry * (1 - risk.take_profit_pct)
        assert abs(r.stop_loss_price - expected_sl) < 0.01
        assert abs(r.take_profit_price - expected_tp) < 0.01

    def test_qty_calculada_con_leverage(self, risk):
        # qty = (capital * leverage) / price
        # capital_to_use = 100 * 0.30 = 30; qty = (30 * 3) / 100 = 0.9
        r = risk.validate("LONG", 100.0, available_capital=100, total_capital=100)
        assert r.is_valid
        expected_qty = (r.capital_to_use * risk.max_leverage) / 100.0
        assert abs(r.quantity - expected_qty) < 0.01
