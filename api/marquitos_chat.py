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
            return {"reply": "🚀 ¡Listo! Estoy encendido y listo para scalpear. Decime con cuánto capital opero (ej: '50 USDT')."}
        return {"reply": "No puedo arrancar: el runner no está inicializado. ¿Está corriendo el bot?"}

    # ── 2. Comando: APAGAR ────────────────────────────────────────────────────
    if _contains_any(msg, _DEACTIVATE_WORDS):
        if _runner is not None:
            capital_final = marquitos_agent.capital
            pnl = marquitos_agent.total_pnl
            _runner.stop_marquitos()
            return {"reply": f"😴 Me apagué. Capital final: {capital_final:.2f} USDT | PnL sesión: {pnl:+.2f} USDT. ¡Hasta la próxima!"}
        return {"reply": "No puedo apagarme: no encuentro el runner."}

    # ── 3. Si está esperando capital → detectar número ────────────────────────
    if marquitos_agent.awaiting_capital:
        amount = _extract_amount(msg)
        if amount and 1.0 <= amount <= 10000.0:
            marquitos_agent.set_capital_from_user(amount)
            return {"reply": f"💰 ¡Perfecto! Voy a operar con {amount:.2f} USDT. Escaneando el mercado cada 5 segundos... ¡A romper el mercado! 🔥"}
        return {"reply": "💬 Marquitos está activo pero esperando capital. Decime con cuánto opero (ej: '50', '100 USDT')."}

    # ── 4. Detectar "operar/comprar [SYMBOL]" → ejecución real ───────────────
    _BUY_WORDS = ["operar", "comprar", "entra", "entrar", "opera", "trade", "comprá",
                  "metele", "metés", "entrá", "compramos"]
    if _contains_any(msg, _BUY_WORDS):
        import re as _re
        # Tokens que NO son símbolos de monedas
        _EXCLUDE = {"USDT", "USD", "STOP", "START", "BUY", "SELL",
                    "TP", "SL", "PNL", "AI", "IA", "CON", "EN", "DE", "LA", "EL",
                    "UNA", "NO", "Y", "A", "ME", "AL", "SIN", "LOS", "LAS"}

        symbol: Optional[str] = None  # type: ignore[name-defined]

        # Prioridad 1: token en MAYÚSCULAS explícito (PEPE, PEPEUSDT, SOL…)
        caps_tokens = _re.findall(r'\b([A-Z]{2,12})\b', req.message)
        for tok in caps_tokens:
            base = tok[:-4] if tok.endswith("USDT") else tok
            if base not in _EXCLUDE and len(base) >= 2:
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
                if candidate not in _EXCLUDE:
                    symbol = candidate if candidate.endswith("USDT") else candidate + "USDT"

        if symbol:
            result = marquitos_agent.force_buy(symbol)
            if result["ok"]:
                return {"reply": (
                    f"🟢 **¡Compré {symbol}!**\n"
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
