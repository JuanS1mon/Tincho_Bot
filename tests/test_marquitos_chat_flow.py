"""
Tests del flujo de onboarding de Marquitos por chat.
"""
import asyncio

from agent.marquitos_agent import marquitos_agent
from api import marquitos_chat


class _DummyRunner:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start_marquitos(self) -> None:
        self.started = True

    def stop_marquitos(self) -> None:
        self.stopped = True


def _run(req: marquitos_chat.MarquitosChatRequest):
    return asyncio.run(marquitos_chat.chat_with_marquitos(req))


def test_activate_requests_symbol_and_amount(monkeypatch):
    marquitos_agent.prepare_new_session()

    dummy = _DummyRunner()
    monkeypatch.setattr("api.status_api._runner", dummy)

    out = _run(marquitos_chat.MarquitosChatRequest(message="activar marquitos", history=[]))

    assert dummy.started is True
    assert "moneda" in out["reply"].lower()
    assert "10 usdt" in out["reply"].lower()


def test_symbol_without_amount_uses_default_10(monkeypatch):
    marquitos_agent.prepare_new_session()

    captured = {"symbol": None, "side": None}

    def fake_force_trade(symbol: str, side: str = "LONG"):
        captured["symbol"] = symbol
        captured["side"] = side
        return {
            "ok": True,
            "symbol": symbol,
            "side": side,
            "price": 100.0,
            "tp": 100.8,
            "sl": 99.7,
            "capital": marquitos_agent.capital,
        }

    monkeypatch.setattr(marquitos_agent, "force_trade", fake_force_trade)

    out = _run(marquitos_chat.MarquitosChatRequest(message="operar pepe", history=[]))

    assert captured["symbol"] == "PEPEUSDT"
    assert captured["side"] == "LONG"
    assert marquitos_agent.capital == 10.0
    assert "trade en pepeusdt" in out["reply"].lower()


def test_amount_out_of_range_is_rejected():
    marquitos_agent.prepare_new_session()
    marquitos_agent.set_symbol_from_user("BTCUSDT")

    out = _run(marquitos_chat.MarquitosChatRequest(message="0.5 usdt", history=[]))

    assert "entre 1 y 10000 usdt" in out["reply"].lower()


def test_force_trade_short_builds_short_position(monkeypatch):
    marquitos_agent.prepare_new_session()
    marquitos_agent.set_capital_from_user(10.0)

    monkeypatch.setattr("agent.marquitos_agent.order_manager.is_symbol_open", lambda _s: True)
    monkeypatch.setattr("agent.marquitos_agent.market_fetcher.get_ticker", lambda _s: {"price": 100.0})

    out = marquitos_agent.force_trade("BTCUSDT", side="SHORT")

    assert out["ok"] is True
    assert marquitos_agent.position is not None
    assert marquitos_agent.position.get("side") == "SHORT"
    assert marquitos_agent.position["take_profit_price"] < marquitos_agent.position["entry_price"]
    assert marquitos_agent.position["stop_loss_price"] > marquitos_agent.position["entry_price"]

    marquitos_agent.position = None
    marquitos_agent.position_symbol = None
    marquitos_agent.position_side = None
