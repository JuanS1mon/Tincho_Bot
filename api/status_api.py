
from __future__ import annotations
from agent.parameters_manager import parameters_manager
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
    POST /marquitos/start    — activar Marquitos (scalper)
    POST /marquitos/stop    — detener Marquitos (scalper)
    GET /marquitos/status    — estado de Marquitos (scalper)
"""

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from tools.portfolio_tool import portfolio_tool, Position
from exchange.order_manager import order_manager
from storage.trade_repository import trade_repository
from storage.state_repository import state_repository
from config.settings import settings
from config.logger import trading_logger as logger

from api.marquitos_state import router as marquitos_router
from api.marquitos_chat import router as marquitos_chat_router

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
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Routers extra
app.include_router(marquitos_router)
app.include_router(marquitos_chat_router)

# Referencia al agente (inyectada desde agent_runner.py)
_agent: Optional["TradingAgent"] = None

# Referencia global al runner (para controlar Marquitos)
_runner: Optional[Any] = None

def set_agent(agent: "TradingAgent") -> None:
    """Inyecta la referencia al agente para que la API pueda leerlo."""
    global _agent
    _agent = agent

def set_runner(runner: Any) -> None:
    global _runner
    _runner = runner


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/agent/status", summary="Estado completo del agente")
async def get_agent_status() -> Dict[str, Any]:
    """Retorna el estado interno completo del agente (ciclo, análisis, última decisión)."""
    if _agent is None:
        raise HTTPException(status_code=503, detail="Agente no inicializado")
    return _agent.get_status()


@app.get("/portfolio", summary="Estado del portafolio")
async def get_portfolio() -> Dict[str, Any]:
    """Retorna capital, PnL, win rate y posiciones abiertas con P&L en tiempo real."""
    portfolio_state = portfolio_tool.get_state_dict()

    # Enriquecer posiciones con current_price y unrealized_pnl
    for sym, pos_dict in portfolio_state.get("positions", {}).items():
        pos = portfolio_tool.positions.get(sym)
        if pos is None:
            continue

        # Si entry_price quedó en 0 localmente, intentar traerlo desde Binance.
        entry_price = pos.entry_price
        if entry_price <= 0:
            try:
                ex_positions = order_manager._client.safe_call(
                    order_manager._client.client.futures_position_information,
                    symbol=sym,
                )
                for p in ex_positions:
                    amt = float(p.get("positionAmt", 0) or 0)
                    if amt == 0:
                        continue
                    ep = float(p.get("entryPrice", 0) or 0)
                    if ep > 0:
                        entry_price = ep
                        pos_dict["entry_price"] = ep
                        break
            except Exception:
                pass

        # Intentar precio actual desde snapshot del agente
        current_price = entry_price
        if _agent is not None and sym in _agent.state.market_snapshots:
            current_price = _agent.state.market_snapshots[sym].price
        else:
            try:
                ticker = order_manager._client.safe_call(
                    order_manager._client.client.futures_symbol_ticker, symbol=sym
                )
                current_price = float(ticker["price"])
            except Exception:
                pass

        if pos.direction == "LONG":
            unrealized_pnl = (current_price - entry_price) * pos.quantity
        else:
            unrealized_pnl = (entry_price - current_price) * pos.quantity
        unrealized_pnl_pct = (unrealized_pnl / pos.capital_used * 100) if pos.capital_used > 0 else 0.0

        pos_dict["current_price"] = round(current_price, 6)
        pos_dict["unrealized_pnl"] = round(unrealized_pnl, 4)
        pos_dict["unrealized_pnl_pct"] = round(unrealized_pnl_pct, 2)

    db_stats = trade_repository.get_stats()
    return {
        "portfolio": portfolio_state,
        "db_stats": db_stats,
    }


@app.get("/positions", summary="Posiciones abiertas")
async def get_positions() -> Dict[str, Any]:
    """Retorna todas las posiciones abiertas con precio actual y P&L no realizado."""
    positions = {}
    for sym, pos in portfolio_tool.positions.items():
        # Si entry local quedó en 0, intentar recuperarlo desde Binance.
        entry_price = pos.entry_price
        if entry_price <= 0:
            try:
                ex_positions = order_manager._client.safe_call(
                    order_manager._client.client.futures_position_information,
                    symbol=sym,
                )
                for p in ex_positions:
                    amt = float(p.get("positionAmt", 0) or 0)
                    if amt == 0:
                        continue
                    ep = float(p.get("entryPrice", 0) or 0)
                    if ep > 0:
                        entry_price = ep
                        break
            except Exception:
                pass

        # Precio actual: snapshot del agente → fallback exchange
        current_price = entry_price
        if _agent is not None and sym in _agent.state.market_snapshots:
            current_price = _agent.state.market_snapshots[sym].price
        else:
            try:
                ticker = order_manager._client.safe_call(
                    order_manager._client.client.futures_symbol_ticker,
                    symbol=sym,
                )
                current_price = float(ticker["price"])
            except Exception:
                pass

        # P&L no realizado
        if pos.direction == "LONG":
            unrealized_pnl = (current_price - entry_price) * pos.quantity
        else:
            unrealized_pnl = (entry_price - current_price) * pos.quantity
        unrealized_pnl_pct = (unrealized_pnl / pos.capital_used * 100) if pos.capital_used > 0 else 0.0

        positions[sym] = {
            "direction": pos.direction,
            "entry_price": entry_price,
            "current_price": current_price,
            "quantity": pos.quantity,
            "capital_used": pos.capital_used,
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "unrealized_pnl": round(unrealized_pnl, 4),
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
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


@app.get("/parameters", summary="Parámetros dinámicos del agente")
async def get_parameters() -> Dict[str, Any]:
    """Retorna los parámetros dinámicos actuales del agente (leverage, risk, etc.)"""
    return parameters_manager.params.to_dict()


# ── Modelos para endpoints POST ───────────────────────────────────────────────

class BullishRequest(BaseModel):
    symbol: str
    pct: float  # fracción del capital disponible, ej. 0.10 = 10%


# ── POST /bullish ─────────────────────────────────────────────────────────────

@app.post("/bullish", summary="Compra manual de meme coin")
async def bullish_buy(req: BullishRequest) -> Dict[str, Any]:
    """
    Compra manualmente una moneda con un porcentaje del capital disponible.
    No debe ser ninguno de los símbolos que ya monitorea el agente.
    """
    if not (0.01 <= req.pct <= 0.50):
        raise HTTPException(status_code=400, detail="pct debe ser entre 0.01 y 0.50")

    symbol = req.symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    if symbol in [s.upper() for s in settings.symbols]:
        raise HTTPException(
            status_code=400,
            detail=f"{symbol} ya es monitoreado por el agente. Elegí otra moneda.",
        )

    available = portfolio_tool.available_capital
    if available < 5.0:
        raise HTTPException(
            status_code=400,
            detail=f"Capital insuficiente: {available:.2f} USDT disponibles",
        )

    capital_to_use = available * req.pct

    # Precio actual de la moneda en futuros
    try:
        ticker = order_manager._client.safe_call(
            order_manager._client.client.futures_symbol_ticker,
            symbol=symbol,
        )
        price = float(ticker["price"])
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo obtener precio de {symbol}: {exc}",
        )

    if price <= 0:
        raise HTTPException(status_code=400, detail=f"Precio inválido para {symbol}")

    quantity = round(capital_to_use / price, 4)
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Cantidad calculada es 0")

    leverage = 2
    dry_run = _agent.dry_run if _agent is not None else True
    order_id: Optional[str] = None

    if not dry_run:
        try:
            order_manager.set_leverage(symbol, leverage)
            order = order_manager.open_long(symbol, quantity, leverage)
            order_id = str(order.get("orderId", "BULLISH"))
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Error ejecutando orden en exchange: {exc}",
            )
    else:
        order_id = "BULLISH_DRY"

    stop_loss = round(price * 0.90, 8)
    take_profit = round(price * 1.30, 8)

    position = Position(
        symbol=symbol,
        direction="LONG",
        entry_price=price,
        quantity=quantity,
        capital_used=round(capital_to_use, 4),
        stop_loss=stop_loss,
        take_profit=take_profit,
        order_id=order_id,
    )
    portfolio_tool.open_position(position)

    logger.info(
        "🐂 BULLISH manual: %s @ %.6f | qty=%.4f | capital=%.2f USDT | dry_run=%s",
        symbol, price, quantity, capital_to_use, dry_run,
    )

    return {
        "status": "ok",
        "symbol": symbol,
        "direction": "LONG",
        "entry_price": price,
        "quantity": quantity,
        "capital_used": round(capital_to_use, 2),
        "leverage": leverage,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "dry_run": dry_run,
    }


# ── POST /bombarda ────────────────────────────────────────────────────────────

@app.post("/bombarda", summary="Cierre de emergencia de todas las posiciones")
async def bombarda() -> Dict[str, Any]:
    """
    Cierra TODAS las posiciones abiertas a precio de mercado de forma inmediata.
    En modo real:
      - Cierra posiciones detectadas en Binance (aunque no estén en el portafolio interno)
      - Cancela órdenes pendientes por símbolo
      - Sincroniza capital final desde Futures
    """
    dry_run = _agent.dry_run if _agent is not None else True
    closed = []
    errors = []

    # Targets a cerrar: unión de posiciones internas + posiciones reales en Binance.
    targets: Dict[str, Dict[str, Any]] = {}
    for symbol, pos in portfolio_tool.positions.copy().items():
        targets[symbol] = {
            "symbol": symbol,
            "direction": pos.direction,
            "quantity": float(pos.quantity),
            "entry_price": float(pos.entry_price),
            "from_portfolio": True,
        }

    if not dry_run:
        try:
            # Cerrar también posiciones que existan en Binance y no estén en memoria local.
            exchange_positions = order_manager._client.safe_call(
                order_manager._client.client.futures_position_information
            )
            for p in exchange_positions:
                amt = float(p.get("positionAmt", 0) or 0)
                if amt == 0:
                    continue
                symbol = str(p.get("symbol", "")).upper()
                if not symbol:
                    continue
                targets[symbol] = {
                    "symbol": symbol,
                    "direction": "LONG" if amt > 0 else "SHORT",
                    "quantity": abs(amt),
                    "entry_price": float(p.get("entryPrice", 0) or 0),
                    "from_portfolio": symbol in portfolio_tool.positions,
                }
        except Exception as exc:
            errors.append({"symbol": "*", "error": f"No se pudieron leer posiciones reales: {exc}"})

        # Cancelar órdenes pendientes de todos los símbolos con open orders.
        try:
            open_orders = order_manager._client.safe_call(
                order_manager._client.client.futures_get_open_orders
            )
            for sym in {str(o.get("symbol", "")).upper() for o in open_orders if o.get("symbol")}:
                try:
                    order_manager._client.safe_call(
                        order_manager._client.client.futures_cancel_all_open_orders,
                        symbol=sym,
                    )
                except Exception as exc:
                    errors.append({"symbol": sym, "error": f"No se pudieron cancelar órdenes: {exc}"})
        except Exception as exc:
            errors.append({"symbol": "*", "error": f"No se pudieron leer órdenes abiertas: {exc}"})

    if not targets:
        return {
            "status": "ok",
            "closed": [],
            "errors": errors,
            "dry_run": dry_run,
            "message": "No hay posiciones abiertas",
        }

    for symbol, t in targets.items():
        direction = t["direction"]
        quantity = float(t["quantity"])

        # Precio actual: snapshot del agente o ticker en exchange.
        exit_price = float(t.get("entry_price", 0) or 0)
        if _agent is not None and symbol in _agent.state.market_snapshots:
            exit_price = _agent.state.market_snapshots[symbol].price
        else:
            try:
                ticker = order_manager._client.safe_call(
                    order_manager._client.client.futures_symbol_ticker,
                    symbol=symbol,
                )
                exit_price = float(ticker["price"])
            except Exception:
                pass

        if not dry_run:
            try:
                side = "BUY" if direction == "LONG" else "SELL"
                order_manager.close_position(symbol, side, quantity)
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})
                continue

        if symbol in portfolio_tool.positions:
            trade = portfolio_tool.close_position(symbol, exit_price, strategy="BOMBARDA")
            if trade:
                closed.append({
                    "symbol": symbol,
                    "direction": direction,
                    "entry_price": trade.entry_price,
                    "exit_price": exit_price,
                    "pnl": trade.pnl,
                    "pnl_pct": trade.pnl_pct,
                    "from_portfolio": True,
                })
            continue

        # Posición estaba en exchange pero no en memoria local.
        closed.append({
            "symbol": symbol,
            "direction": direction,
            "entry_price": float(t.get("entry_price", 0) or 0),
            "exit_price": exit_price,
            "pnl": None,
            "pnl_pct": None,
            "from_portfolio": False,
        })

    # Tras cerrar todo, refrescar capital desde Binance Futures.
    portfolio_tool.sync_from_exchange(force=True)

    logger.info("💣 BOMBARDA ejecutada: %d posición(es) cerrada(s) | dry_run=%s", len(closed), dry_run)

    return {
        "status": "ok",
        "closed": closed,
        "errors": errors,
        "dry_run": dry_run,
        "message": f"{len(closed)} posición(es) cerrada(s). En USDⓈ-M, el saldo queda en USDT al cerrar.",
    }


# ── POST /chat  (Tincho2 — asesor conversacional) ────────────────────────────

class ChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


# Carga la personalidad de Tincho2 desde tincho2.md (editable en caliente)
_TINCHO2_MD_PATH = Path(__file__).parent.parent / "tincho2.md"
_TINCHO2_SYSTEM_CACHE: Optional[str] = None


def _load_tincho2_prompt() -> str:
    """
    Extrae el system prompt de tincho2.md (sección '## 🧠 Prompt del Sistema').
    Cachea en memoria; se recarga si el archivo fue modificado.
    """
    global _TINCHO2_SYSTEM_CACHE
    if not _TINCHO2_MD_PATH.exists():
        logger.warning("tincho2.md no encontrado, usando prompt de fallback")
        return (
            "Sos Tincho2, un asesor de trading cripto directo y experimentado. "
            "Tenés acceso al estado actual del portafolio y el mercado. "
            "Respondé en el idioma del usuario. Sé conciso y nunca inventes datos."
        )
    raw = _TINCHO2_MD_PATH.read_text(encoding="utf-8")
    import re as _re
    match = _re.search(r"##\s+🧠\s+Prompt del Sistema\s*\n(.*?)(?=\n##\s|\Z)", raw, _re.DOTALL)
    if match:
        return match.group(1).strip()
    # Si no hay sección marcada, usar todo el archivo como prompt
    return raw.strip()


# Meme coins a monitorear en tiempo real para el chat de Tincho2
_MEME_COINS = [
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT",
    "FLOKIUSDT", "MEMEUSDT", "NEIROUSDT", "DOGSUSDT", "NOTUSDT",
    "1000SATSUSDT", "TURBOUSDT", "MAGAUSDT", "PNUTUSDT",
]


def _fetch_meme_coins_context() -> str:
    """
    Busca datos en tiempo real de meme coins populares desde Binance Futures.
    Retorna un bloque de texto con precio, cambio 24h y volumen.
    """
    lines: list[str] = []
    fetched: list[dict] = []

    for symbol in _MEME_COINS:
        try:
            ticker = order_manager._client.safe_call(
                order_manager._client.client.futures_ticker,
                symbol=symbol,
            )
            if not ticker or "lastPrice" not in ticker:
                continue
            price = float(ticker["lastPrice"])
            change_pct = float(ticker.get("priceChangePercent", 0))
            volume_usdt = float(ticker.get("quoteVolume", 0))
            if price <= 0:
                continue
            fetched.append({
                "symbol": symbol.replace("USDT", ""),
                "price": price,
                "change_pct": change_pct,
                "volume_usdt": volume_usdt,
            })
        except Exception:
            continue  # moneda no disponible en este exchange/testnet

    if not fetched:
        return ""

    # Ordenar por volumen 24h descendente (las más activas primero)
    fetched.sort(key=lambda x: x["volume_usdt"], reverse=True)

    lines.append("\n=== MEME COINS (datos en tiempo real de Binance Futures) ===")
    for c in fetched:
        arrow = "🟢" if c["change_pct"] >= 0 else "🔴"
        vol_m = c["volume_usdt"] / 1_000_000
        lines.append(
            f"{arrow} {c['symbol']}: ${c['price']:.6g} | {c['change_pct']:+.2f}% (24h) | vol {vol_m:.1f}M USDT"
        )

    return "\n".join(lines)


def _build_market_context() -> str:
    """Construye un bloque de texto con el estado actual del bot para pasarle a la IA."""
    lines: list[str] = []

    # Portfolio
    p = portfolio_tool.get_state_dict()
    dry_run = _agent.dry_run if _agent is not None else True
    mode = "DRY-RUN (simulación)" if dry_run else "LIVE (dinero real)"
    lines.append(f"=== PORTAFOLIO ({mode}) ===")
    lines.append(f"Capital total: {p['capital']:.2f} USDT")
    lines.append(f"Capital disponible: {p['available_capital']:.2f} USDT")
    lines.append(f"PnL acumulado: {p['total_pnl']:+.4f} USDT ({p['total_pnl'] / max(p['initial_capital'], 1) * 100:+.2f}%)")
    lines.append(f"Win rate: {p['win_rate'] * 100:.1f}% ({p['winning_trades']}/{p['total_trades']} trades)")
    lines.append(f"Posiciones abiertas: {p['open_positions']}")

    if p.get("positions"):
        for sym, pos in p["positions"].items():
            lines.append(f"  • {sym} {pos['direction']} @ entrada {pos['entry_price']:.4f} | SL: {pos['stop_loss']:.4f} | TP: {pos['take_profit']:.4f}")

    # Mercado y señales (BTC/ETH del agente)
    if _agent is not None and _agent.state.market_snapshots:
        lines.append("\n=== MERCADO (BTC / ETH) ===")
        for sym, snap in _agent.state.market_snapshots.items():
            sig = _agent.state.signals.get(sym)
            signal_str = f"{sig.signal} (conf {sig.confidence:.0%}, est. {sig.strategy})" if sig else "?"
            lines.append(
                f"{sym}: precio={snap.price:.4f} | tendencia={snap.trend} | RSI={snap.rsi:.1f} "
                f"| vol={snap.volume_trend} | OI={snap.oi_trend} | funding={snap.funding_rate*100:.4f}% | señal={signal_str}"
            )
            if sig and sig.reason:
                lines.append(f"  Razón: {sig.reason}")

    # Meme coins en tiempo real
    meme_ctx = _fetch_meme_coins_context()
    if meme_ctx:
        lines.append(meme_ctx)

    # Estado del agente
    if _agent is not None:
        st = _agent.state
        lines.append(f"\n=== AGENTE ===")
        lines.append(f"Estado: {st.status} | Ciclo: {st.cycle}")
        if st.last_error:
            lines.append(f"Último error: {st.last_error}")

    # Parámetros de trading actuales (ajustables por la IA)
    lines.append(f"\n=== PARÁMETROS DE TRADING ACTUALES ===")
    lines.append(parameters_manager.summary())

    return "\n".join(lines)


@app.post("/chat", summary="Chat con Tincho2 — asesor IA")
async def chat_with_tincho2(req: ChatRequest) -> Dict[str, Any]:
    """
    Endpoint conversacional. Pasa el mensaje del usuario + historial a DeepSeek
    con contexto del estado actual del bot como system prompt.
    Si la respuesta incluye [PARAMS:{...}], aplica los cambios al parameters_manager.
    """
    import json as _json
    import re as _re
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url if settings.ai_base_url and "openai.com" not in settings.ai_base_url else None,
        timeout=30.0,
    )

    # Contexto dinámico del bot
    market_ctx = _build_market_context()
    tincho2_prompt = _load_tincho2_prompt()
    system_content = f"{tincho2_prompt}\n\n{market_ctx}"

    # Construir historial de mensajes
    messages: list[Dict[str, str]] = [{"role": "system", "content": system_content}]
    for msg in req.history[-12:]:
        if msg.role in ("user", "assistant"):
            messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": req.message})

    try:
        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.7,
            max_tokens=600,
        )
        reply = response.choices[0].message.content or "No pude generar una respuesta."
    except Exception as exc:
        logger.error("Tincho2 chat error: %s", exc)
        raise HTTPException(status_code=502, detail=f"Error consultando IA: {exc}")

    # Detectar etiqueta [PARAMS:{...}] y aplicar cambios de modo robusto
    params_applied: Dict[str, Any] | None = None
    params_match = _re.search(r"\[PARAMS:(\{.*?\})\]", reply, _re.DOTALL)
    if params_match:
        raw_json = params_match.group(1)
        # Intentar corregir JSON malformado (comas, comillas, etc.)
        try:
            adjustments = _json.loads(raw_json)
        except Exception:
            try:
                # Reparar comillas simples/dobles y eliminar trailing commas
                fixed = raw_json.replace("'", '"').replace(",}", "}").replace(",]", "]")
                adjustments = _json.loads(fixed)
            except Exception as exc:
                logger.warning("No se pudo parsear [PARAMS:...]: %s", exc)
                adjustments = None
        if adjustments:
            # Si el usuario pidió modo tryhard, chill o putita, aplicar preset
            modo = None
            req_text = req.message.lower()
            if any(w in req_text for w in ["tryhard", "agresivo", "a morir"]):
                modo = "tryhard"
            elif any(w in req_text for w in ["chill", "balanceado", "normal"]):
                modo = "chill"
            elif any(w in req_text for w in ["putita", "conservador", "cauteloso", "con miedo"]):
                modo = "putita"
            if modo:
                presets = {
                    "tryhard": {"leverage": 20, "stop_loss": 0.04, "take_profit": 0.15, "max_capital_per_trade": 0.50, "risk_per_trade": 0.03},
                    "chill":   {"leverage": 10, "stop_loss": 0.03, "take_profit": 0.12, "max_capital_per_trade": 0.35, "risk_per_trade": 0.02},
                    "putita":  {"leverage": 5,  "stop_loss": 0.015, "take_profit": 0.06, "max_capital_per_trade": 0.15, "risk_per_trade": 0.005},
                }
                adjustments.update(presets[modo])
            changed = parameters_manager.apply_adjustments(
                adjustments,
                reason=f"Tincho2 chat: {req.message[:80]}"
            )
            if changed:
                params_applied = adjustments
                logger.info("⚙️ Tincho2 ajustó parámetros: %s", adjustments)
        # Limpiar la etiqueta del texto visible
        reply = _re.sub(r"\s*\[PARAMS:\{.*?\}\]", "", reply, flags=_re.DOTALL).strip()

    logger.info("💬 Tincho2: user=%r | reply=%r", req.message[:60], reply[:80])
    return {"reply": reply, "paramsApplied": params_applied}


@app.post("/marquitos/start", summary="Llamar a Marquitos (activar scalper)")
async def start_marquitos():
    if _runner is None:
        raise HTTPException(status_code=503, detail="Runner no inicializado")
    _runner.start_marquitos()
    return {"status": "ok", "message": "Marquitos activado"}


@app.post("/marquitos/stop", summary="Detener a Marquitos (scalper)")
async def stop_marquitos():
    if _runner is None:
        raise HTTPException(status_code=503, detail="Runner no inicializado")
    _runner.stop_marquitos()
    return {"status": "ok", "message": "Marquitos detenido"}


@app.get("/marquitos/status", summary="Estado de Marquitos (scalper)")
async def marquitos_status():
    if _runner is None:
        raise HTTPException(status_code=503, detail="Runner no inicializado")
    return {"active": bool(_runner._marquitos_active)}

