"""
Domain Entity - Trade Signal
=============================
Representa la señal de trading generada por la IA.
Incluye validación del JSON recibido.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

from config.logger import get_logger

logger = get_logger(__name__)

# Schema esperado del JSON de la IA
REQUIRED_FIELDS = {"invest", "confidence", "capital_usage", "allocation", "market_state", "reasoning"}
REQUIRED_ALLOCATION_FIELDS = {"BTC", "ETH"}


@dataclass
class TradeSignal:
    """
    Señal de trading generada por el motor de IA.
    
    Campos:
        invest: Si se debe invertir (True/False).
        confidence: Nivel de confianza (0.0 - 1.0).
        capital_usage: Proporción del capital a usar (0.0 - 1.0).
        allocation: Distribución del capital entre activos (ej: {"BTC": 0.7, "ETH": 0.3}).
        market_state: Estado general del mercado.
        reasoning: Explicación de la decisión.
    """
    invest: bool = False
    confidence: float = 0.0
    capital_usage: float = 0.0
    allocation: Dict[str, float] = field(default_factory=dict)
    market_state: str = "unknown"
    reasoning: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    raw_response: Optional[dict] = None

    @classmethod
    def from_ai_response(cls, data: dict) -> "TradeSignal":
        """
        Crea un TradeSignal desde la respuesta JSON de la IA.
        Valida el schema y aplica valores seguros por defecto.
        
        Args:
            data: Diccionario parseado del JSON de la IA.
            
        Returns:
            TradeSignal validado.
            
        Raises:
            ValueError: Si el JSON no tiene la estructura esperada.
        """
        # Validar campos requeridos
        missing = REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise ValueError(f"Campos faltantes en respuesta IA: {missing}")

        # Validar allocation
        allocation = data.get("allocation", {})
        if not isinstance(allocation, dict):
            raise ValueError(f"allocation debe ser un diccionario, recibido: {type(allocation)}")

        # Normalizar claves de allocation (aceptar BTCUSDT o BTC)
        normalized_allocation = {}
        for key, value in allocation.items():
            clean_key = key.replace("USDT", "")
            normalized_allocation[clean_key] = float(value)

        # Validar que allocation suma ~1.0
        alloc_sum = sum(normalized_allocation.values())
        if alloc_sum > 0 and abs(alloc_sum - 1.0) > 0.05:
            logger.warning(
                f"Allocation no suma 1.0 (suma={alloc_sum:.2f}). Normalizando..."
            )
            normalized_allocation = {
                k: v / alloc_sum for k, v in normalized_allocation.items()
            }

        # Validar rangos
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
        capital_usage = max(0.0, min(1.0, float(data.get("capital_usage", 0))))

        signal = cls(
            invest=bool(data.get("invest", False)),
            confidence=confidence,
            capital_usage=capital_usage,
            allocation=normalized_allocation,
            market_state=str(data.get("market_state", "unknown")),
            reasoning=str(data.get("reasoning", "")),
            raw_response=data,
        )

        logger.info(
            f"TradeSignal creado: invest={signal.invest}, "
            f"confidence={signal.confidence:.2f}, "
            f"capital_usage={signal.capital_usage:.2f}, "
            f"allocation={signal.allocation}"
        )
        return signal

    @classmethod
    def no_trade(cls, reason: str = "Condiciones no favorables") -> "TradeSignal":
        """Crea un TradeSignal que indica NO operar."""
        return cls(
            invest=False,
            confidence=0.0,
            capital_usage=0.0,
            allocation={},
            market_state="unfavorable",
            reasoning=reason,
        )

    def to_dict(self) -> dict:
        """Serializa el signal para almacenamiento."""
        return {
            "invest": self.invest,
            "confidence": round(self.confidence, 4),
            "capital_usage": round(self.capital_usage, 4),
            "allocation": {k: round(v, 4) for k, v in self.allocation.items()},
            "market_state": self.market_state,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp.isoformat(),
        }
