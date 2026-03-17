"""
Pruebas unitarias para tool calling en ai/llm_client.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ai.llm_client import LLMClient


class _DummyFunction:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _DummyToolCall:
    def __init__(self, name: str, arguments: str) -> None:
        self.function = _DummyFunction(name, arguments)


class _DummyMessage:
    def __init__(self, content: str, tool_calls=None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class _DummyChoice:
    def __init__(self, message: _DummyMessage) -> None:
        self.message = message


class _DummyResponse:
    def __init__(self, message: _DummyMessage) -> None:
        self.choices = [_DummyChoice(message)]


class _DummyCompletions:
    def __init__(self, response: _DummyResponse) -> None:
        self._response = response

    def create(self, **_kwargs):
        return self._response


class _DummyChat:
    def __init__(self, response: _DummyResponse) -> None:
        self.completions = _DummyCompletions(response)


class _DummyClient:
    def __init__(self, response: _DummyResponse) -> None:
        self.chat = _DummyChat(response)


def _build_client_with_response(message: _DummyMessage) -> LLMClient:
    client = LLMClient()
    client._client = _DummyClient(_DummyResponse(message))  # type: ignore[attr-defined]
    return client


def test_decide_with_tools_returns_direct_tool_call():
    msg = _DummyMessage(
        content="",
        tool_calls=[
            _DummyToolCall(
                "open_position",
                '{"symbol":"BTCUSDT","direction":"LONG","capital_usage":0.25,"reasoning":"setup fuerte"}',
            )
        ],
    )
    client = _build_client_with_response(msg)

    result = client.decide_with_tools(
        system_prompt="sys",
        user_prompt="user",
        tools=[],
    )

    assert result is not None
    assert result.tool_name == "open_position"
    assert result.arguments["symbol"] == "BTCUSDT"
    assert result.arguments["direction"] == "LONG"
    assert result.arguments["capital_usage"] == 0.25
    assert result.fallback_decision is None


def test_decide_with_tools_fallback_open_position_from_legacy_json():
    legacy_json = (
        '{"trade": true, "symbol": "ETHUSDT", "direction": "SHORT", '
        '"capital_usage": 0.2, "confidence": 0.9, "reasoning": "impulso bajista"}'
    )
    msg = _DummyMessage(content=legacy_json, tool_calls=[])
    client = _build_client_with_response(msg)

    result = client.decide_with_tools(
        system_prompt="sys",
        user_prompt="user",
        tools=[],
    )

    assert result is not None
    assert result.tool_name == "open_position"
    assert result.arguments["symbol"] == "ETHUSDT"
    assert result.arguments["direction"] == "SHORT"
    assert result.fallback_decision is not None


def test_decide_with_tools_fallback_adjust_parameters_priority():
    legacy_json = (
        '{"trade": true, "symbol": "BTCUSDT", "direction": "LONG", '
        '"capital_usage": 0.1, "confidence": 0.8, "reasoning": "bajar riesgo", '
        '"parameter_adjustments": {"leverage": 8, "stop_loss": 0.02}}'
    )
    msg = _DummyMessage(content=legacy_json, tool_calls=[])
    client = _build_client_with_response(msg)

    result = client.decide_with_tools(
        system_prompt="sys",
        user_prompt="user",
        tools=[],
    )

    assert result is not None
    assert result.tool_name == "adjust_parameters"
    assert result.arguments["leverage"] == 8
    assert result.arguments["stop_loss"] == 0.02
    assert "reasoning" in result.arguments
