"""
storage/trade_repository.py
============================
CRUD para la colección 'trades' en MongoDB.
Almacena el registro completo de cada trade ejecutado.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from storage.database import db_manager
from config.logger import trading_logger as logger, error_logger


class TradeRepository:
    """Acceso a datos para trades históricos."""

    @property
    def _col(self):
        return db_manager.db["trades"]

    def save_trade(self, trade_data: Dict[str, Any]) -> Optional[str]:
        """
        Persiste un trade en la base de datos.
        trade_data debe incluir: symbol, direction, entry_price, exit_price,
        quantity, pnl, pnl_pct, strategy.
        Retorna el ID del documento insertado.
        """
        doc = {
            **trade_data,
            "timestamp": datetime.utcnow(),
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            result = self._col.insert_one(doc)
            logger.debug("Trade guardado: %s", result.inserted_id)
            return str(result.inserted_id)
        except Exception as exc:
            error_logger.error("TradeRepository.save_trade error: %s", exc)
            return None

    def save_execution_log(self, log_data: Dict[str, Any]) -> Optional[str]:
        """Guarda el log completo de un ciclo del agente (análisis + decisión)."""
        doc = {
            **log_data,
            "timestamp": datetime.utcnow(),
        }
        try:
            result = db_manager.db["execution_logs"].insert_one(doc)
            return str(result.inserted_id)
        except Exception as exc:
            error_logger.error("TradeRepository.save_execution_log error: %s", exc)
            return None

    def get_recent_trades(self, symbol: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Retorna los trades más recientes, opcionalmente filtrados por símbolo."""
        try:
            query = {"symbol": symbol} if symbol else {}
            cursor = self._col.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
            return list(cursor)
        except Exception as exc:
            error_logger.error("TradeRepository.get_recent_trades error: %s", exc)
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Estadísticas globales de todos los trades registrados."""
        try:
            pipeline = [
                {
                    "$group": {
                        "_id": None,
                        "total_trades": {"$sum": 1},
                        "total_pnl": {"$sum": "$pnl"},
                        "avg_pnl": {"$avg": "$pnl"},
                        "winning_trades": {
                            "$sum": {"$cond": [{"$gt": ["$pnl", 0]}, 1, 0]}
                        },
                    }
                }
            ]
            result = list(self._col.aggregate(pipeline))
            if result:
                r = result[0]
                total = r.get("total_trades", 0)
                wins = r.get("winning_trades", 0)
                return {
                    "total_trades": total,
                    "total_pnl": round(r.get("total_pnl", 0), 4),
                    "avg_pnl": round(r.get("avg_pnl", 0), 4),
                    "win_rate": round(wins / total, 4) if total > 0 else 0,
                }
            return {"total_trades": 0, "total_pnl": 0, "avg_pnl": 0, "win_rate": 0}
        except Exception as exc:
            error_logger.error("TradeRepository.get_stats error: %s", exc)
            return {}


# Instancia global
trade_repository = TradeRepository()
