"""
api/marquitos_chat.py
=====================
Chat con Marquitos: IA con personalidad de scalper, basada en marquitos.md
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import re as _re
import unicodedata
from typing import Any, Dict, Optional

router = APIRouter()

_ACTIVATE_WORDS = ["activar", "prender", "arrancar", "enciende", "enciendete", "start", "activate", "arranca"]
_DEACTIVATE_WORDS = ["apaga", "apagar", "stop", "detener", "desactivar", "apágate", "parar", "para"]
_SYMBOL_EXCLUDE = {
    "USDT", "USD", "STOP", "START", "BUY", "SELL", "TP", "SL", "PNL", "AI", "IA",
    "CON", "EN", "DE", "LA", "EL", "UNA", "NO", "Y", "A", "ME", "AL", "SIN", "LOS", "LAS",
    "ACTIVAR", "ARRANCAR", "OPERAR", "COMPRAR", "ENTRAR", "MONEDA", "MONTO",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return text.lower().strip()


def _contains_any(text: str, words: list[str]) -> bool:
    n = _normalize(text)
    return any(_normalize(w) in n for w in words)


def _extract_amount(text: str) -> float | None:
    m = _re.search(r"\b(\d{1,6}(?:[.,]\d{1,2})?)\b", text)
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            pass
    return None


def _extract_symbol(text: str) -> str | None:
    caps_tokens = _re.findall(r"\b([A-Z]{2,12})\b", text)
    for tok in caps_tokens:
        base = tok[:-4] if tok.endswith("USDT") else tok
        if base not in _SYMBOL_EXCLUDE and len(base) >= 2:
            return base + "USDT"

    lower_match = _re.search(
        r"(?:moneda|symbol|simbolo|símbolo|operar|comprar|entrar|opera|trade|compr[aá]|entr[aá])"
        r"(?:\s+(?:con|en|a|el|la|de))?\s+([a-zA-Z]{2,12})",
        text,
        _re.IGNORECASE,
    )
    if lower_match:
        candidate = lower_match.group(1).upper()
        if candidate not in _SYMBOL_EXCLUDE:
            return candidate if candidate.endswith("USDT") else candidate + "USDT"
    return None


class MarquitosChatRequest(BaseModel):
    message: str
    history: list[dict] = []


def _load_marquitos_prompt() -> str:
    """Carga el contenido de marquitos.md como system prompt."""
    md_path = Path(__file__).parent.parent / "marquitos.md"
    if not md_path.exists():
        return (
            "Sos Marquitos, un scalper cripto adicto a TODO. "
            "Respondé siempre como un adicto a la acción, sin miedo al riesgo, y con humor. "
            "Sos veloz, brutalmente honesto y no te detenés ante nada."
        )
    return md_path.read_text(encoding="utf-8").strip()


def _build_marquitos_context() -> str:
    """Contexto del estado actual de Marquitos para la IA."""
    lines: list[str] = []
    try:
        from agent.marquitos_agent import marquitos_agent
        s = marquitos_agent.get_state_dict()
        lines.append("=== ESTADO DE MARQUITOS ===")
        lines.append(f"Capital: {s['capital']:.2f} USDT")
        lines.append(f"PnL total: {s['total_pnl']:+.4f} USDT")
        lines.append(f"Trades ganados: {s['trades_won']}/{s['trades_total']}")
        if s.get("last_ai_decision"):
            lines.append(f"Última decisión IA: {s['last_ai_decision']}")
        if s.get("position"):
            p = s["position"]
            lines.append(
                f"Posición activa: {p['symbol']} @ entrada {p['entry_price']:.6g} | "
                f"TP: {p['take_profit_price']:.6g} (+0.8%) | SL: {p['stop_loss_price']:.6g} (-0.3%)"
            )
        else:
            lines.append("Sin posición activa.")
        if s.get("last_signals"):
            lines.append("Últimas señales escaneadas:")
            for sym, sig in list(s["last_signals"].items())[:5]:
                lines.append(f"  {sym}: {sig}")
    except Exception:
        pass
    return "\n".join(lines)


@router.post("/marquitos/chat", summary="Chat con Marquitos — scalper IA")
async def chat_with_marquitos(req: MarquitosChatRequest) -> Dict[str, Any]:
    from agent.marquitos_agent import marquitos_agent
    from agent.marquitos_agent import DEFAULT_TRADE_AMOUNT_USDT

    # ── Intentar obtener referencia al runner ─────────────────────────────────
    try:
        from api.status_api import _runner
    except ImportError:
        _runner = None

    msg = req.message

    # ── 1. Comando: ACTIVAR ───────────────────────────────────────────────────
    if _contains_any(msg, _ACTIVATE_WORDS):
        if _runner is not None:
            _runner.start_marquitos()
            return {
                "reply": (
                    "🚀 ¡Marquitos online! Para arrancar decime:\n"
                    "1) qué moneda querés (ej: BTCUSDT o PEPE)\n"
                    "2) cuánto monto para esa moneda (ej: 10 USDT)\n"
                    f"Si no indicás monto, uso {DEFAULT_TRADE_AMOUNT_USDT:.0f} USDT por defecto."
                )
            }
        return {"reply": "No puedo arrancar: el runner no está inicializado. ¿Está corriendo el bot?"}

    # ── 2. Comando: APAGAR ────────────────────────────────────────────────────
    if _contains_any(msg, _DEACTIVATE_WORDS):
        if _runner is not None:
            capital_final = marquitos_agent.capital
            pnl = marquitos_agent.total_pnl
            _runner.stop_marquitos()
            return {"reply": f"😴 Me apagué. Capital final: {capital_final:.2f} USDT | PnL sesión: {pnl:+.2f} USDT. ¡Hasta la próxima!"}
        return {"reply": "No puedo apagarme: no encuentro el runner."}

    # ── 3. Onboarding: pedir moneda + monto ───────────────────────────────────
    if marquitos_agent.awaiting_symbol or marquitos_agent.awaiting_capital:
        symbol = _extract_symbol(msg)
        amount = _extract_amount(msg)

        if symbol and marquitos_agent.awaiting_symbol:
            marquitos_agent.set_symbol_from_user(symbol)

        if amount is not None:
            if 1.0 <= amount <= 10000.0:
                marquitos_agent.set_capital_from_user(amount)
            else:
                return {"reply": "⚠️ El monto debe estar entre 1 y 10000 USDT."}

        if not marquitos_agent.awaiting_symbol and marquitos_agent.awaiting_capital:
            marquitos_agent.set_capital_from_user(DEFAULT_TRADE_AMOUNT_USDT)
            amount = DEFAULT_TRADE_AMOUNT_USDT

        if marquitos_agent.awaiting_symbol:
            return {
                "reply": (
                    "💬 Decime la moneda que querés operar primero "
                    "(ej: BTCUSDT, ETH o PEPE)."
                )
            }

        if marquitos_agent.awaiting_capital:
            return {
                "reply": (
                    "💬 Perfecto, ahora decime el monto para esa moneda "
                    "(si querés, podés dejar 10 USDT por defecto)."
                )
            }

        chosen_symbol = marquitos_agent.preferred_symbol
        if not chosen_symbol:
            return {"reply": "No pude detectar la moneda. Probá con algo como 'PEPE' o 'BTCUSDT'."}

        side = "SHORT" if _contains_any(msg, ["short", "vender", "venta", "bajar", "cae", "a la baja"]) else "LONG"
        result = marquitos_agent.force_trade(chosen_symbol, side=side)
        if result["ok"]:
            side_label = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
            return {
                "reply": (
                    f"{side_label} **¡Trade en {chosen_symbol}!**\n"
                    f"📍 Entrada: `{result['price']:.8g}` USDT\n"
                    f"💰 Monto asignado: {result['capital']:.2f} USDT\n"
                    f"✅ TP: `{result['tp']:.8g}` (+0.8%)\n"
                    f"🛑 SL: `{result['sl']:.8g}` (-0.3%)\n"
                    "Objetivo: ganancia rápida cuando el mercado esté calmo y limpio."
                )
            }
        return {"reply": f"❌ {result['error']}"}

    # ── 4. Detectar "operar/comprar [SYMBOL]" → ejecución real ───────────────
    _BUY_WORDS = ["operar", "comprar", "entra", "entrar", "opera", "trade", "comprá",
                  "metele", "metés", "entrá", "compramos", "long"]
    _SELL_WORDS = ["vender", "venta", "short", "ponete short", "a la baja", "baja"]
    if _contains_any(msg, _BUY_WORDS) or _contains_any(msg, _SELL_WORDS):
        import re as _re
        symbol: Optional[str] = None  # type: ignore[name-defined]

        # Prioridad 1: token en MAYÚSCULAS explícito (PEPE, PEPEUSDT, SOL…)
        caps_tokens = _re.findall(r'\b([A-Z]{2,12})\b', req.message)
        for tok in caps_tokens:
            base = tok[:-4] if tok.endswith("USDT") else tok
            if base not in _SYMBOL_EXCLUDE and len(base) >= 2:
                symbol = base + "USDT"
                break

        # Prioridad 2: palabra en minúsculas justo después de la buy-word
        # ej: "opera pepe", "comprá solana", "entrá con bnb"
        if not symbol:
            after = _re.search(
                r'(?:operar?|comprar?|entr[aá]r?|opera|trade|comprá|metele|compramos)'
                r'(?:\s+(?:con|en|a|el|la))?\s+([a-zA-Z]{2,12})',
                req.message, _re.IGNORECASE,
            )
            if after:
                candidate = after.group(1).upper()
                if candidate not in _SYMBOL_EXCLUDE:
                    symbol = candidate if candidate.endswith("USDT") else candidate + "USDT"

        if symbol:
            side = "SHORT" if _contains_any(msg, _SELL_WORDS) else "LONG"
            result = marquitos_agent.force_trade(symbol, side=side)
            if result["ok"]:
                side_label = "🟢 LONG" if side == "LONG" else "🔴 SHORT"
                return {"reply": (
                    f"{side_label} **¡Trade en {symbol}!**\n"
                    f"📍 Entrada: `{result['price']:.8g}` USDT\n"
                    f"💰 Capital: {result['capital']:.2f} USDT ×40x\n"
                    f"✅ TP: `{result['tp']:.8g}` (+0.8%)\n"
                    f"🛑 SL: `{result['sl']:.8g}` (-0.3%)\n"
                    f"Monitoreando cada 5 segundos. ¡A esperar el pump! 🔥"
                )}
            else:
                return {"reply": f"❌ {result['error']}"}

    from openai import OpenAI
    from config.settings import settings

    client = OpenAI(
        api_key=settings.ai_api_key,
        base_url=settings.ai_base_url if settings.ai_base_url and "openai.com" not in settings.ai_base_url else None,
        timeout=30.0,
    )

    marquitos_prompt = _load_marquitos_prompt()
    state_ctx = _build_marquitos_context()
    system_content = (
        f"{marquitos_prompt}\n\n"
        f"{state_ctx}\n\n"
        "Respondé SIEMPRE como Marquitos: breve, directo, adicto a la acción, con humor."
    )

    messages: list[Dict[str, str]] = [{"role": "system", "content": system_content}]
    for msg in req.history[-12:]:
        role = msg.get("role", "user")
        if role == "marquitos":
            role = "assistant"
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    try:
        response = client.chat.completions.create(
            model=settings.ai_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0.85,
            max_tokens=400,
        )
        reply = response.choices[0].message.content or "No pude generar una respuesta."
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Error consultando IA: {exc}")

    return {"reply": reply}
