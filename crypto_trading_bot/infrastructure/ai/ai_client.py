"""
Infrastructure - AI Client
============================
Cliente genérico para comunicación con modelos de IA.
Configurado para DeepSeek (activo) con soporte comentado para OpenAI y Gemini.
Usa el SDK de OpenAI (compatible con DeepSeek).
Parsea y valida respuestas JSON con schema estricto.
"""

import json
import time
from typing import Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger("ai")

# Schema esperado de la respuesta
EXPECTED_SCHEMA = {
    "invest": bool,
    "confidence": (int, float),
    "capital_usage": (int, float),
    "allocation": dict,
    "market_state": str,
    "reasoning": str,
}


class AIClient:
    """
    Cliente de IA para decisiones de trading.
    
    Proveedores soportados:
      - DeepSeek (activo): base_url=https://api.deepseek.com, model=deepseek-chat
      - OpenAI (comentado): base_url=https://api.openai.com/v1, model=gpt-4o
      - Gemini (comentado): via endpoint compatible con OpenAI
    """

    def __init__(self):
        self.client = None
        self.model = settings.AI_MODEL
        self._max_retries = 3
        self._init_client()

    def _init_client(self) -> None:
        """Inicializa el cliente de IA según el proveedor configurado."""
        try:
            from openai import OpenAI

            # --- DeepSeek (activo) ---
            if settings.AI_PROVIDER == "deepseek":
                self.client = OpenAI(
                    api_key=settings.AI_API_KEY,
                    base_url=settings.AI_BASE_URL,  # https://api.deepseek.com
                )
                logger.info(f"🤖 IA inicializada: DeepSeek ({self.model})")

            # --- OpenAI (descomentar para usar) ---
            # elif settings.AI_PROVIDER == "openai":
            #     self.client = OpenAI(
            #         api_key=settings.AI_API_KEY,
            #         base_url="https://api.openai.com/v1",
            #     )
            #     logger.info(f"🤖 IA inicializada: OpenAI ({self.model})")

            # --- Gemini (descomentar para usar) ---
            # elif settings.AI_PROVIDER == "gemini":
            #     self.client = OpenAI(
            #         api_key=settings.AI_API_KEY,
            #         base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            #     )
            #     logger.info(f"🤖 IA inicializada: Gemini ({self.model})")

            else:
                # Default: intentar DeepSeek
                self.client = OpenAI(
                    api_key=settings.AI_API_KEY,
                    base_url=settings.AI_BASE_URL,
                )
                logger.warning(
                    f"Proveedor '{settings.AI_PROVIDER}' no reconocido, "
                    f"usando DeepSeek por defecto"
                )

        except ImportError:
            logger.error(
                "❌ Paquete 'openai' no instalado. Ejecutar: pip install openai"
            )
        except Exception as e:
            logger.error(f"❌ Error inicializando cliente IA: {e}")

    def get_trading_decision(
        self, system_prompt: str, user_prompt: str
    ) -> Optional[dict]:
        """
        Envía el prompt a la IA y obtiene una decisión de trading.
        
        Args:
            system_prompt: Prompt del sistema (rol del analista).
            user_prompt: Datos de mercado formateados.
            
        Returns:
            Diccionario con la decisión de trading, o None si falla.
        """
        if not self.client:
            logger.error("Cliente IA no inicializado")
            return None

        for attempt in range(1, self._max_retries + 1):
            try:
                logger.info(f"📤 Enviando prompt a {settings.AI_PROVIDER} (intento {attempt})")

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,  # Baja temperatura para consistencia
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                )

                # Extraer contenido
                content = response.choices[0].message.content
                logger.info(f"📥 Respuesta recibida de {settings.AI_PROVIDER}")
                logger.debug(f"AI Raw Response: {content}")

                # Parsear JSON
                decision = self._parse_response(content)
                if decision:
                    return decision

                logger.warning(f"Respuesta inválida en intento {attempt}")

            except Exception as e:
                logger.error(f"Error en comunicación con IA (intento {attempt}): {e}")
                if attempt < self._max_retries:
                    time.sleep(2 ** attempt)

        logger.error(f"No se pudo obtener decisión de IA después de {self._max_retries} intentos")
        return None

    def _parse_response(self, content: str) -> Optional[dict]:
        """
        Parsea y valida la respuesta JSON de la IA.
        
        Args:
            content: String con el JSON de la respuesta.
            
        Returns:
            Diccionario validado o None si la respuesta es inválida.
        """
        if not content:
            logger.error("Respuesta vacía de la IA")
            return None

        try:
            # Limpiar posible contenido extra alrededor del JSON
            content = content.strip()
            if content.startswith("```"):
                # Eliminar bloques de código markdown
                lines = content.split("\n")
                content = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )

            data = json.loads(content)

            # Validar schema
            if not self._validate_schema(data):
                return None

            return data

        except json.JSONDecodeError as e:
            logger.error(f"Error parseando JSON de IA: {e}")
            logger.debug(f"Contenido recibido: {content[:500]}")
            return None

    def _validate_schema(self, data: dict) -> bool:
        """
        Valida que la respuesta tiene la estructura esperada.
        
        Schema esperado:
        {
            "invest": bool,
            "confidence": float (0-1),
            "capital_usage": float (0-1),
            "allocation": {"BTC": float, "ETH": float},
            "market_state": str,
            "reasoning": str
        }
        """
        for field, expected_type in EXPECTED_SCHEMA.items():
            if field not in data:
                logger.error(f"Campo faltante en respuesta IA: '{field}'")
                return False

            value = data[field]
            if not isinstance(value, expected_type):
                logger.error(
                    f"Tipo incorrecto para '{field}': "
                    f"esperado {expected_type}, recibido {type(value)}"
                )
                return False

        # Validar rangos numéricos
        if not (0 <= data["confidence"] <= 1):
            logger.warning(f"Confidence fuera de rango: {data['confidence']}")

        if not (0 <= data["capital_usage"] <= 1):
            logger.warning(f"Capital_usage fuera de rango: {data['capital_usage']}")

        # Validar allocation tiene BTC o ETH
        allocation = data["allocation"]
        if not any(k in allocation for k in ["BTC", "ETH", "BTCUSDT", "ETHUSDT"]):
            logger.warning("Allocation no contiene BTC ni ETH")

        return True
