"""
api/status_api.py
==================
API HTTP con FastAPI para exponer el estado interno del agente.
Permite conectar una interfaz gráfica externa sin modificar el agente.

Endpoints:
  GET /agent/status        — estado completo del agente
  GET /portfolio           — estado del portafolio
  GET /positions           — posiciones abiertas
  GET /market-analysis     — último análisis de mercado por símbolo
  GET /logs                — últimas líneas de los logs
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from tools.portfolio_tool import portfolio_tool
from storage.trade_repository import trade_repository
from storage.state_repository import state_repository
from config.settings import settings
from config.logger import trading_logger as logger

if TYPE_CHECKING:
    from agent.trading_agent import TradingAgent

# ── App FastAPI ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Tincho Bot — Trading Agent API",
    description="API de estado para el agente autónomo de trading de criptomonedas.",
    version="1.0.0",
)

# CORS — permite conexión desde cualquier frontend local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Referencia al agente (inyectada desde agent_runner.py)
_agent: Optional["TradingAgent"] = None


def set_agent(agent: "TradingAgent") -> None:
    """Inyecta la referencia al agente para que la API pueda leerlo."""
    global _agent
    _agent = agent


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/agent/status", summary="Estado completo del agente")
async def get_agent_status() -> Dict[str, Any]:
    """Retorna el estado interno completo del agente (ciclo, análisis, última decisión)."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agente no inicializado")
    return _agent.get_status()


@app.get("/portfolio", summary="Estado del portafolio")
async def get_portfolio() -> Dict[str, Any]:
    """Retorna capital, PnL, win rate y posiciones abiertas."""
    portfolio_state = portfolio_tool.get_state_dict()
    db_stats = trade_repository.get_stats()
    return {
        "portfolio": portfolio_state,
        "db_stats": db_stats,
    }


@app.get("/positions", summary="Posiciones abiertas")
async def get_positions() -> Dict[str, Any]:
    """Retorna todas las posiciones abiertas actualmente."""
    positions = {
        sym: {
            "direction": pos.direction,
            "entry_price": pos.entry_price,
            "quantity": pos.quantity,
            "capital_used": pos.capital_used,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
        }
        for sym, pos in portfolio_tool.positions.items()
    }
    return {"positions": positions, "count": len(positions)}


@app.get("/market-analysis", summary="Último análisis de mercado")
async def get_market_analysis() -> Dict[str, Any]:
    """Retorna el último snapshot de análisis de mercado por símbolo."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agente no inicializado")
    return {
        "market_snapshots": {
            sym: {
                "price": snap.price,
                "trend": snap.trend,
                "rsi": snap.rsi,
                "sma20": snap.sma20,
                "sma50": snap.sma50,
                "volume_trend": snap.volume_trend,
                "oi_trend": snap.oi_trend,
                "oi_signal": snap.oi_signal,
                "funding_rate": snap.funding_rate,
                "orderbook_imbalance": snap.orderbook_imbalance,
                "liquidation_signal": snap.liquidation_signal,
            }
            for sym, snap in _agent.state.market_snapshots.items()
        },
        "signals": {
            sym: {
                "signal": sig.signal,
                "strategy": sig.strategy,
                "confidence": sig.confidence,
                "reason": sig.reason,
            }
            for sym, sig in _agent.state.signals.items()
        },
    }


@app.get("/logs", summary="Últimas entradas de log")
async def get_logs(lines: int = 50) -> Dict[str, Any]:
    """
    Retorna las últimas N líneas del log de trading.
    Query param: lines (default 50, max 500)
    """
    lines = max(1, min(lines, 500))

    trading_log_path = settings.logs_dir / "trading.log"
    error_log_path = settings.logs_dir / "errors.log"

    def tail_file(path: Path, n: int) -> list:
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            return [line.rstrip() for line in all_lines[-n:]]
        except Exception:
            return []

    return {
        "trading_log": tail_file(trading_log_path, lines),
        "error_log": tail_file(error_log_path, min(lines, 50)),
        "cycle_logs": _agent.state.cycle_logs[-lines:] if _agent else [],
    }


@app.get("/trades", summary="Historial de trades")
async def get_trades(symbol: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
    """Retorna los últimos trades ejecutados desde MongoDB."""
    trades = trade_repository.get_recent_trades(symbol=symbol, limit=min(limit, 100))
    return {"trades": trades, "count": len(trades)}


@app.get("/health", summary="Health check")
async def health() -> Dict[str, str]:
    return {"status": "ok", "service": "tincho-bot"}
