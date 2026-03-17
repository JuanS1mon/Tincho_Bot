"""
ai/llm_client.py
================
Cliente para el modelo de lenguaje (DeepSeek por defecto).
Usa el SDK de OpenAI con base_url configurable → soporta
DeepSeek, OpenAI, Groq u otros proveedores compatibles.

Valida y parsea la respuesta JSON del modelo.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config.agent_config import agent_config
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


@dataclass
class AIDecision:
    trade: bool
    symbol: str
    direction: str                          # LONG | SHORT
    capital_usage: float                    # fracción del capital del símbolo (0.0 – 0.50)
    confidence: float                       # 0.0 – 1.0
    reasoning: str
    raw_response: str                       # respuesta cruda para logs
    parameter_adjustments: Optional[Dict[str, Any]] = None  # ajustes sugeridos por la IA


@dataclass
class ToolCallResult:
    tool_name: str
    arguments: Dict[str, Any]
    raw_response: str
    reasoning: str = ""
    fallback_decision: Optional[AIDecision] = None


class LLMClient:
    """Interfaz con el modelo de lenguaje para validación de decisiones."""

    # Tiempo máximo de espera por respuesta del modelo
    _TIMEOUT: float = 30.0

    def __init__(self) -> None:
        self._client = self._build_client()

    def _build_client(self) -> OpenAI:
        """Construye el cliente OpenAI apuntando al proveedor configurado."""
        kwargs: dict = {
            "api_key": settings.ai_api_key,
            "timeout": self._TIMEOUT,
        }
        # DeepSeek, Groq y otros usan base_url diferente a OpenAI
        if settings.ai_base_url and "openai.com" not in settings.ai_base_url:
            kwargs["base_url"] = settings.ai_base_url

        return OpenAI(**kwargs)

    def decide(self, user_prompt: str) -> Optional[AIDecision]:
        """
        Envía el prompt al modelo y retorna la decisión parseada.
        Retorna None si la llamada falla o la respuesta es inválida.
        """
        try:
            logger.debug("Consultando IA (%s/%s)...", settings.ai_provider, settings.ai_model)
            response = self._client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": agent_config.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or ""
            logger.debug("Respuesta IA raw: %s", raw[:200])
            return self._parse_response(raw)

        except Exception as exc:
            error_logger.error("LLMClient.decide error: %s", exc)
            return None

    def _parse_response(self, raw: str) -> Optional[AIDecision]:
        """Extrae y valida el JSON de la respuesta del modelo."""
        # Limpiar markdown si el modelo lo incluyó
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()

        # Buscar el primer bloque JSON completo
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            error_logger.error("LLMClient: no se encontró JSON en la respuesta: %s", raw[:200])
            return None

        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            error_logger.error("LLMClient: JSON inválido: %s | raw=%s", exc, raw[:200])
            return None

        # Validar campos requeridos
        required = {"trade", "symbol", "direction", "capital_usage", "confidence"}
        missing = required - data.keys()
        if missing:
            error_logger.error("LLMClient: campos faltantes en JSON: %s", missing)
            return None

        # Sanitizar valores
        try:
            # parameter_adjustments es opcional: None si ausente o null
            raw_adjustments = data.get("parameter_adjustments")
            param_adj = raw_adjustments if isinstance(raw_adjustments, dict) else None

            decision = AIDecision(
                trade=bool(data["trade"]),
                symbol=str(data["symbol"]).upper().strip(),
                direction=str(data["direction"]).upper().strip(),
                capital_usage=max(0.0, min(float(data["capital_usage"]), 0.50)),
                confidence=max(0.0, min(float(data["confidence"]), 1.0)),
                reasoning=str(data.get("reasoning", ""))[:200],
                raw_response=raw,
                parameter_adjustments=param_adj,
            )
        except (TypeError, ValueError) as exc:
            error_logger.error("LLMClient: error sanitizando respuesta: %s", exc)
            return None

        action = "OPERAR" if decision.trade else "NO OPERAR"
        logger.info(
            "[%s] 🤖 IA → %s | conf=%.0f%% | %s",
            decision.symbol, action,
            decision.confidence * 100,
            decision.reasoning,
        )
        return decision

    def market_overview(self, user_prompt: str) -> Optional[Dict[str, Any]]:
        """
        Envía un prompt de análisis global de mercado y retorna solo
        {"reasoning": str, "parameter_adjustments": dict | None}.
        No requiere los campos de trade (trade/symbol/direction/etc.).
        """
        try:
            response = self._client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": agent_config.system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=256,
            )
            raw = response.choices[0].message.content or ""
        except Exception as exc:
            error_logger.error("LLMClient.market_overview error: %s", exc)
            return None

        # Parsear JSON simplificado
        cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            error_logger.warning("market_overview: no JSON en respuesta: %s", raw[:200])
            return None
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError as exc:
            error_logger.warning("market_overview: JSON inválido: %s", exc)
            return None

        reasoning = str(data.get("reasoning", ""))[:200]
        raw_adj = data.get("parameter_adjustments")
        param_adj = raw_adj if isinstance(raw_adj, dict) else None

        logger.info("🌍 Tincho1 market overview: %s | params=%s", reasoning, param_adj)
        return {"reasoning": reasoning, "parameter_adjustments": param_adj}

    def decide_with_tools(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        tools: List[Dict[str, Any]],
        temperature: float = 0.2,
        max_tokens: int = 300,
    ) -> Optional[ToolCallResult]:
        """
        Ejecuta function calling con fallback al parser JSON legacy.

        - Si el modelo devuelve tool_calls, retorna la primera tool.
        - Si no devuelve tools, intenta parsear JSON legacy con _parse_response().
        """
        try:
            response = self._client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                tools=tools,
                tool_choice="auto",
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            error_logger.error("LLMClient.decide_with_tools error: %s", exc)
            return None

        message = response.choices[0].message
        raw = message.content or ""
        tool_calls = getattr(message, "tool_calls", None) or []

        if tool_calls:
            call = tool_calls[0]
            fn = getattr(call, "function", None)
            if fn is None:
                error_logger.error("decide_with_tools: tool_call sin function")
                return None

            name = str(getattr(fn, "name", "") or "").strip()
            args_raw = str(getattr(fn, "arguments", "") or "{}").strip()
            try:
                args = json.loads(args_raw) if args_raw else {}
            except json.JSONDecodeError:
                logger.warning("decide_with_tools: argumentos no-JSON, se usa dict vacio")
                args = {}

            logger.info("🤖 Tool selected: %s | args=%s", name, args)
            return ToolCallResult(
                tool_name=name,
                arguments=args,
                raw_response=raw,
                reasoning=raw[:200],
            )

        # Fallback legacy: modelo no emitio tool calls.
        legacy_decision = self._parse_response(raw)
        if legacy_decision is None:
            logger.warning("decide_with_tools: sin tool_calls y fallback legacy invalido")
            return None

        fallback_name = "open_position" if legacy_decision.trade else "skip_trade"
        fallback_args: Dict[str, Any]
        if legacy_decision.trade:
            fallback_args = {
                "symbol": legacy_decision.symbol,
                "direction": legacy_decision.direction,
                "capital_usage": legacy_decision.capital_usage,
                "reasoning": legacy_decision.reasoning,
            }
        else:
            fallback_args = {
                "reason": legacy_decision.reasoning or "La IA decidio no operar",
            }

        if legacy_decision.parameter_adjustments:
            fallback_name = "adjust_parameters"
            fallback_args = dict(legacy_decision.parameter_adjustments)
            if legacy_decision.reasoning:
                fallback_args["reasoning"] = legacy_decision.reasoning

        logger.info("decide_with_tools: fallback legacy -> %s", fallback_name)
        return ToolCallResult(
            tool_name=fallback_name,
            arguments=fallback_args,
            raw_response=raw,
            reasoning=legacy_decision.reasoning,
            fallback_decision=legacy_decision,
        )


# Instancia global
llm_client = LLMClient()
