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
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from ai.decision_prompt import SYSTEM_PROMPT
from config.settings import settings
from config.logger import trading_logger as logger, error_logger


@dataclass
class AIDecision:
    trade: bool
    symbol: str
    direction: str           # LONG | SHORT
    capital_usage: float     # fracción del capital total (0.0 – 0.30)
    confidence: float        # 0.0 – 1.0
    reasoning: str
    raw_response: str        # respuesta cruda para logs


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
                    {"role": "system", "content": SYSTEM_PROMPT},
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
            decision = AIDecision(
                trade=bool(data["trade"]),
                symbol=str(data["symbol"]).upper().strip(),
                direction=str(data["direction"]).upper().strip(),
                capital_usage=max(0.0, min(float(data["capital_usage"]), settings.max_capital_per_trade)),
                confidence=max(0.0, min(float(data["confidence"]), 1.0)),
                reasoning=str(data.get("reasoning", ""))[:200],
                raw_response=raw,
            )
        except (TypeError, ValueError) as exc:
            error_logger.error("LLMClient: error sanitizando respuesta: %s", exc)
            return None

        logger.info(
            "Decisión IA: trade=%s symbol=%s dir=%s capital=%.0f%% confidence=%.0f%% | %s",
            decision.trade, decision.symbol, decision.direction,
            decision.capital_usage * 100, decision.confidence * 100,
            decision.reasoning,
        )
        return decision


# Instancia global
llm_client = LLMClient()
