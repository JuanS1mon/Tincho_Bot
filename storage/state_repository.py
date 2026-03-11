"""
storage/state_repository.py
============================
Persiste y carga el estado del agente en MongoDB.
Permite que el agente recupere su último estado si se reinicia.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from storage.database import db_manager
from config.logger import trading_logger as logger, error_logger


class StateRepository:
    """Guarda y carga el estado serializado del agente."""

    @property
    def _col(self):
        return db_manager.db["agent_states"]

    def save_state(self, state: Dict[str, Any]) -> Optional[str]:
        """
        Guarda el estado actual del agente (portafolio + posiciones).
        Usa upsert para mantener siempre el estado más reciente accesible.
        """
        doc = {
            **state,
            "timestamp": datetime.utcnow(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        try:
            result = self._col.replace_one(
                {"_id": "current_state"},
                {"_id": "current_state", **doc},
                upsert=True,
            )
            # También guardar snapshot histórico
            self._col.insert_one({**doc, "snapshot": True})
            return "current_state"
        except Exception as exc:
            error_logger.error("StateRepository.save_state error: %s", exc)
            return None

    def load_latest_state(self) -> Optional[Dict[str, Any]]:
        """Carga el estado más reciente del agente."""
        try:
            doc = self._col.find_one({"_id": "current_state"})
            if doc:
                doc.pop("_id", None)
            return doc
        except Exception as exc:
            error_logger.error("StateRepository.load_latest_state error: %s", exc)
            return None

    def save_market_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Persiste un snapshot del estado del mercado en cada ciclo."""
        try:
            db_manager.db["market_snapshots"].insert_one({
                **snapshot,
                "timestamp": datetime.utcnow(),
            })
        except Exception as exc:
            error_logger.error("StateRepository.save_market_snapshot error: %s", exc)

    def get_market_history(self, symbol: str, limit: int = 100) -> list:
        """Retorna historial de snapshots de mercado para un símbolo."""
        try:
            cursor = (
                db_manager.db["market_snapshots"]
                .find({"symbol": symbol}, {"_id": 0})
                .sort("timestamp", -1)
                .limit(limit)
            )
            return list(cursor)
        except Exception as exc:
            error_logger.error("StateRepository.get_market_history error: %s", exc)
            return []


# Instancia global
state_repository = StateRepository()
