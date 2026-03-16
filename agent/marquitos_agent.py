"""
agent/marquitos_agent.py
=========================
Marquitos — Agente Scalper IA Ultra-Rápido.

Arquitectura de agente:
  - Sin activación → modo CHAT puro (habla con el usuario)
  - Activado + capital asignado → modo TRADING:
      1. Usa CoinFinder para buscar meme coins / altcoins volátiles
      2. Analiza los candidatos técnicamente
      3. Llama a DeepSeek para elegir la mejor moneda
      4. Abre 1 LONG con todo el capital
      5. Monitorea cada 5s:
           → TP >= +0.8%: VENDE
           → SL <= -0.3%: VENDE
           → Entre -0.3% y +0.8%: IA decide si cerrar o aguantar

  El cerebro (marquitos_brain) aprende qué monedas y parámetros funcionan.
"""
from __future__ import annotations

import json
import time
import threading
from typing import Any, Dict, List, Optional

from exchange.market_fetcher import market_fetcher
from exchange.order_manager import order_manager
from tools.indicator_tool import indicator_tool
from tools.marquitos_coin_finder import coin_finder
from agent.marquitos_brain import marquitos_brain
from config.settings import settings
from config.logger import trading_logger as logger, error_logger

# ── Configuración ─────────────────────────────────────────────────────────────
MARQUITOS_TIMEFRAME: str = "1m"
MIN_GREEN_CANDLES: int = 2
MARQUITOS_LEVERAGE: int = 40         # apalancamiento alto — el jonqui no se frena
TAKE_PROFIT_PCT: float = 0.008       # 0.8% → sell
STOP_LOSS_PCT: float = 0.003         # 0.3% → sell para no perder
SCAN_INTERVAL: int = 10              # segundos entre scans sin posición
MONITOR_INTERVAL: int = 5            # segundos entre chequeos de posición
AI_HOLD_ZONE_PCT: float = 0.001      # si PnL entre -0.1% y +0.4% → consulta IA


def _build_llm_client():
    """Crea el cliente OpenAI apuntando a DeepSeek (o al proveedor configurado)."""
    from openai import OpenAI
    kwargs: Dict[str, Any] = {"api_key": settings.ai_api_key, "timeout": 20.0}
    if settings.ai_base_url and "openai.com" not in settings.ai_base_url:
        kwargs["base_url"] = settings.ai_base_url
    return OpenAI(**kwargs)


def _load_marquitos_md() -> str:
    """Carga marquitos.md como system prompt."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "marquitos.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else "Soy Marquitos, scalper cripto."


class MarquitosAgent:
    """
    Marquitos: agente scalper IA ultra-rápido.

    Estados internos:
      - awaiting_capital=True  → activado pero esperando capital del usuario
      - awaiting_capital=False + running → escaneando y operando
    """

    def __init__(self, dry_run: bool = True) -> None:
        self.dry_run = dry_run
        self.capital: float = 0.0
        self.initial_capital: float = 0.0
        self.position: Optional[dict] = None
        self.position_symbol: Optional[str] = None
        self._stop_event = threading.Event()
        self._running = False
        self.total_pnl: float = 0.0
        self.trades_won: int = 0
        self.trades_total: int = 0
        self.brain = marquitos_brain
        self.awaiting_capital: bool = True
        self.last_signals: Dict[str, Any] = {}
        # Última decisión de la IA (para debug/chat)
        self.last_ai_decision: str = ""

    # ── Control externo ───────────────────────────────────────────────────────

    def set_capital_from_user(self, amount: float) -> None:
        self.capital = round(amount, 2)
        self.initial_capital = self.capital
        self.awaiting_capital = False
        logger.info("🐺 [Marquitos] Capital asignado: %.2f USDT", self.capital)

    def force_buy(self, symbol: str) -> dict:
        """Compra inmediata de un símbolo específico sin esperar el ciclo de scan."""
        symbol = symbol.upper()
        if not symbol.endswith("USDT"):
            symbol += "USDT"

        if self.position is not None:
            return {"ok": False, "error": f"Ya estoy operando {self.position_symbol}. Esperá que cierre."}
        if self.awaiting_capital:
            return {"ok": False, "error": "Primero decime con cuánto capital opero."}
        if self.capital <= 0:
            return {"ok": False, "error": "Capital agotado."}

        try:
            ticker = market_fetcher.get_ticker(symbol)
            price = float(ticker["price"])
        except Exception as exc:
            return {"ok": False, "error": f"Error obteniendo precio de {symbol}: {exc}"}

        from tools.marquitos_coin_finder import MEME_COINS
        category = "meme" if symbol in MEME_COINS else "altcoin"

        entry = {
            "symbol": symbol,
            "price": price,
            "current_price": price,
            "change_pct": 0,
            "category": category,
        }
        self._open_position(entry)

        if self.position is not None:
            return {
                "ok": True,
                "symbol": symbol,
                "price": price,
                "tp": self.position["take_profit_price"],
                "sl": self.position["stop_loss_price"],
                "capital": self.capital,
            }
        return {"ok": False, "error": "No se pudo abrir la posición."}

    def stop(self) -> None:
        self._stop_event.set()

    def get_state_dict(self) -> dict:
        state: dict = {
            "capital": self.capital,
            "initial_capital": self.initial_capital,
            "total_pnl": self.total_pnl,
            "trades_won": self.trades_won,
            "trades_total": self.trades_total,
            "running": self._running,
            "awaiting_capital": self.awaiting_capital,
            "last_signals": self.last_signals,
            "last_ai_decision": self.last_ai_decision,
            "position": None,
        }
        if self.position is not None:
            state["position"] = {
                "symbol": self.position_symbol,
                "entry_price": self.position["entry_price"],
                "current_price": self.position.get("current_price", self.position["entry_price"]),
                "take_profit_price": self.position["take_profit_price"],
                "stop_loss_price": self.position["stop_loss_price"],
                "quantity": self.position["quantity"],
                "open_time": self.position["open_time"],
                "pnl": self.position.get("pnl", 0.0),
                "pnl_pct": self.position.get("pnl_pct", 0.0),
                "change_pct_24h": self.position.get("change_pct_24h", 0),
                "category": self.position.get("category", "altcoin"),
                "capital_used": round(self.position["entry_price"] * self.position["quantity"], 4),
            }
        return state

    def get_market_signals_summary(self) -> dict:
        return self.last_signals

    # ── Loop principal ────────────────────────────────────────────────────────

    def start(self) -> None:
        self._stop_event.clear()
        self._running = True
        logger.info(
            "🐺 [Marquitos] INICIADO | capital=%.2f USDT | dry_run=%s | %s",
            self.capital, self.dry_run, self.brain.report(),
        )
        while not self._stop_event.is_set():
            if self.awaiting_capital:
                self._stop_event.wait(timeout=2)
                continue
            try:
                if self.position is not None:
                    self._monitor_position()
                    self._stop_event.wait(timeout=MONITOR_INTERVAL)
                else:
                    self._scan_and_trade()
                    self._stop_event.wait(timeout=SCAN_INTERVAL)
            except Exception as exc:
                error_logger.error("🐺 [Marquitos] Error en ciclo: %s", exc)
                self._stop_event.wait(timeout=SCAN_INTERVAL)

        self._running = False
        logger.info(
            "🐺 [Marquitos] DETENIDO | PnL=%+.4f USDT | trades: %d/%d",
            self.total_pnl, self.trades_won, self.trades_total,
        )

    # ── Escaneo y selección ───────────────────────────────────────────────────

    def _scan_and_trade(self) -> None:
        """
        1. CoinFinder busca meme coins / altcoins con movimiento hoy.
        2. IA elige cuál comprar (sin filtros técnicos restrictivos).
        3. Abre posición y espera TP +0.8% o SL -0.3%.
        """
        logger.info("🔍 [Marquitos] Escaneando mercado...")

        candidates = coin_finder.scan(top_n=12)
        if not candidates:
            logger.info("🐺 [Marquitos] Sin candidatos hoy, esperando...")
            return

        # Resumen de señales visible en frontend/chat
        self.last_signals = {
            c["symbol"]: (
                f"📈 {c['change_pct']:+.1f}% 24h | "
                f"vol={c['volume_usdt']/1_000_000:.1f}M | "
                f"{'🎰 meme' if c['is_meme'] else 'altcoin'}"
            )
            for c in candidates[:8]
        }

        # IA elige la moneda
        chosen = self._ai_pick_coin(candidates)
        if chosen is None:
            logger.info("🐺 [Marquitos] IA decidió no operar ahora.")
            return

        self._open_position(chosen)

    # ── IA: elección de moneda ────────────────────────────────────────────────

    def _ai_pick_coin(self, candidates: List[dict]) -> Optional[dict]:
        """
        Envía la lista de candidatos a DeepSeek y recibe cuál operar.
        Responde JSON: {"symbol": "PEPEUSDT", "reason": "..."} o {"symbol": null, "reason": "..."}.
        """
        try:
            lines: List[str] = []
            for i, c in enumerate(candidates, 1):
                lines.append(
                    f"{i}. {c['symbol']} | cambio24h={c['change_pct']:+.1f}% | "
                    f"momentum_1m={c.get('momentum_5c', 0):.3f}% | "
                    f"RSI={c.get('rsi', '?')} | "
                    f"velas_verdes={c.get('green_candles', 0)} | "
                    f"volumen={c.get('volume_usdt', 0)/1_000_000:.1f}M USDT | "
                    f"precio={c.get('current_price', c['price']):.8g}"
                )
            candidates_text = "\n".join(lines)

            user_prompt = (
                f"CAPITAL DISPONIBLE: {self.capital:.2f} USDT\n"
                f"TP objetivo: +0.8% | SL automático: -0.3%\n\n"
                f"CANDIDATOS PARA SCALPING LONG AHORA:\n{candidates_text}\n\n"
                f"Elegí UNA sola moneda para entrar AHORA o decí null si ninguna vale la pena.\n"
                f"Respondé SOLO JSON válido sin nada extra:\n"
                f'{{ "symbol": "SIMBOLOUSDT" o null, "reason": "..." }}'
            )

            client = _build_llm_client()
            resp = client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": _load_marquitos_md()},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=120,
            )
            raw = resp.choices[0].message.content or ""
            logger.info("🐺 [Marquitos] IA raw: %s", raw[:150])

            # Parsear JSON de la respuesta
            raw_clean = raw.strip()
            # Extraer primer bloque JSON si viene envuelto en markdown
            import re
            m = re.search(r"\{.*\}", raw_clean, re.DOTALL)
            if not m:
                return None
            data = json.loads(m.group(0))
            symbol = data.get("symbol")
            reason = data.get("reason", "")
            self.last_ai_decision = f"Elegido: {symbol} — {reason}" if symbol else f"No operar — {reason}"
            logger.info("🐺 [Marquitos] IA eligió: %s | %s", symbol, reason)

            if not symbol:
                return None

            # Buscar el candidato elegido en la lista
            for c in candidates:
                if c["symbol"] == symbol:
                    return c

            # Si la IA devolvió un símbolo fuera de la lista, ignorar
            logger.warning("🐺 [Marquitos] IA eligió símbolo no listado: %s", symbol)
            return None

        except Exception as exc:
            error_logger.error("🐺 [Marquitos] _ai_pick_coin error: %s", exc)
            # Fallback: tomar el primer candidato técnico sin IA
            logger.info("🐺 [Marquitos] Fallback sin IA: usando primer candidato")
            return candidates[0] if candidates else None

    # ── Apertura de posición ──────────────────────────────────────────────────

    def _open_position(self, entry: dict) -> None:
        symbol = entry["symbol"]
        price = float(entry.get("current_price", entry["price"]))

        if self.capital <= 0:
            logger.warning("🐺 [Marquitos] Capital agotado.")
            return

        quantity = round(self.capital / price, 4)
        if quantity <= 0:
            return

        tp_price = round(price * (1 + TAKE_PROFIT_PCT), 8)
        sl_price = round(price * (1 - STOP_LOSS_PCT), 8)

        if not self.dry_run:
            try:
                order_manager.set_leverage(symbol, MARQUITOS_LEVERAGE)
                order_manager.open_long(symbol, quantity)
            except Exception as exc:
                error_logger.error("🐺 [Marquitos] Error abriendo %s: %s", symbol, exc)
                return

        self.position = {
            "entry_price": price,
            "current_price": price,
            "quantity": quantity,
            "take_profit_price": tp_price,
            "stop_loss_price": sl_price,
            "open_time": time.time(),
            "pnl": 0.0,
            "pnl_pct": 0.0,
            "change_pct_24h": entry.get("change_pct", 0),
            "category": entry.get("category", "altcoin"),
        }
        self.position_symbol = symbol

        logger.info(
            "🐺 [Marquitos] 🟢 LONG %s @ %.8g | qty=%.4f | "
            "TP=%.8g (+%.1f%%) | SL=%.8g (-%.1f%%) | dry=%s",
            symbol, price, quantity,
            tp_price, TAKE_PROFIT_PCT * 100,
            sl_price, STOP_LOSS_PCT * 100,
            self.dry_run,
        )

    # ── Monitoreo de posición ─────────────────────────────────────────────────

    def _monitor_position(self) -> None:
        if self.position is None or self.position_symbol is None:
            return

        symbol = self.position_symbol
        pos = self.position
        hold_secs = time.time() - pos["open_time"]

        try:
            ticker = market_fetcher.get_ticker(symbol)
            current_price = float(ticker["price"])
        except Exception as exc:
            error_logger.error("🐺 [Marquitos] Error precio %s: %s", symbol, exc)
            logger.warning("🐺 [Marquitos] No pude obtener precio de %s, reintentando en %ds...", symbol, MONITOR_INTERVAL)
            return

        pnl = (current_price - pos["entry_price"]) * pos["quantity"]
        pnl_pct = (current_price - pos["entry_price"]) / pos["entry_price"]

        # Actualizar estado en tiempo real para el frontend
        pos["current_price"] = current_price
        pos["pnl"] = round(pnl, 6)
        pos["pnl_pct"] = round(pnl_pct * 100, 4)

        hit_tp = pnl_pct >= TAKE_PROFIT_PCT
        hit_sl = pnl_pct <= -STOP_LOSS_PCT
        timeout = hold_secs >= self.brain.max_hold_seconds

        if hit_tp:
            logger.info(
                "🐺 [Marquitos] ✅ TP %s @ %.8g | PnL=%+.4f USDT (+%.2f%%) | %.0fs",
                symbol, current_price, pnl, pnl_pct * 100, hold_secs,
            )
            self._close_position(pnl, pnl_pct, win=True)

        elif hit_sl:
            logger.info(
                "🐺 [Marquitos] ❌ SL -0.3%% %s @ %.8g | PnL=%.4f USDT (%.2f%%) | %.0fs",
                symbol, current_price, pnl, pnl_pct * 100, hold_secs,
            )
            self._close_position(pnl, pnl_pct, win=False)

        elif timeout:
            logger.info(
                "🐺 [Marquitos] ⏱ Timeout %s @ %.8g | PnL=%.4f USDT (%.2f%%) | %.0fs",
                symbol, current_price, pnl, pnl_pct * 100, hold_secs,
            )
            self._close_position(pnl, pnl_pct, win=pnl > 0)

        else:
            logger.info(
                "🐺 [Marquitos] 👁 %s | precio=%.8g | TP=%.8g | SL=%.8g | "
                "PnL=%+.4f (%.2f%%) | %.0fs",
                symbol, current_price,
                pos["take_profit_price"], pos["stop_loss_price"],
                pnl, pnl_pct * 100, hold_secs,
            )

    # ── IA: ¿cerrar posición? ─────────────────────────────────────────────────

    def _ai_should_close(
        self,
        symbol: str,
        current_price: float,
        pnl_pct: float,
        hold_secs: float,
        reason: str,
    ) -> bool:
        """
        Pregunta a DeepSeek si debe cerrar la posición antes de tiempo.
        Por defecto cierra (True) si la IA falla.
        """
        try:
            pos = self.position
            if pos is None:
                return True

            user_prompt = (
                f"Posición abierta en {symbol}.\n"
                f"Entrada: {pos['entry_price']:.8g} | Precio actual: {current_price:.8g}\n"
                f"PnL actual: {pnl_pct*100:.2f}% | Tiempo abierta: {hold_secs:.0f}s\n"
                f"TP objetivo: +0.8% | SL automático: -0.3%\n"
                f"Motivo de consulta: {reason}\n\n"
                f"¿Cierro la posición ahora o la aguanto un poco más?\n"
                f"Respondé SOLO JSON sin nada extra:\n"
                f'{{ "action": "close" o "hold", "reason": "..." }}'
            )

            client = _build_llm_client()
            resp = client.chat.completions.create(
                model=settings.ai_model,
                messages=[
                    {"role": "system", "content": _load_marquitos_md()},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=80,
            )
            raw = (resp.choices[0].message.content or "").strip()

            import re
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not m:
                return True
            data = json.loads(m.group(0))
            action = data.get("action", "close")
            ai_reason = data.get("reason", "")
            self.last_ai_decision = f"{action.upper()} posición — {ai_reason}"
            logger.info("🐺 [Marquitos] IA monitoreo: %s | %s", action, ai_reason)
            return action == "close"

        except Exception as exc:
            error_logger.error("🐺 [Marquitos] _ai_should_close error: %s", exc)
            return True  # seguro: cierra si falla la IA

    # ── Cierre de posición ────────────────────────────────────────────────────

    def _close_position(self, pnl: float, pnl_pct: float, win: bool) -> None:
        pos = self.position
        symbol = self.position_symbol
        if pos is None or symbol is None:
            return

        hold_secs = time.time() - pos["open_time"]

        if not self.dry_run:
            try:
                order_manager.close_position(symbol, "BUY", pos["quantity"])
            except Exception as exc:
                error_logger.error("🐺 [Marquitos] Error cerrando %s: %s", symbol, exc)

        self.capital = round(self.capital + pnl, 4)
        self.total_pnl = round(self.total_pnl + pnl, 4)
        self.trades_total += 1
        if win:
            self.trades_won += 1

        if win:
            self.brain.on_win(
                symbol=symbol,
                momentum=pos.get("momentum_5c", 0),
                rsi=pos.get("rsi"),
                pnl_pct=pnl_pct,
                hold_secs=hold_secs,
            )
        else:
            self.brain.on_loss(
                symbol=symbol,
                momentum=pos.get("momentum_5c", 0),
                rsi=pos.get("rsi"),
                pnl_pct=pnl_pct,
                hold_secs=hold_secs,
            )

        wr = (self.trades_won / self.trades_total * 100) if self.trades_total > 0 else 0
        logger.info(
            "🐺 [Marquitos] %s | capital=%.2f USDT | PnL_total=%+.4f | "
            "wr=%.0f%% (%d/%d) | %s",
            "✅ WIN" if win else "❌ LOSS",
            self.capital, self.total_pnl,
            wr, self.trades_won, self.trades_total,
            self.brain.report(),
        )

        self.position = None
        self.position_symbol = None


# ── Instancia global ──────────────────────────────────────────────────────────
marquitos_agent = MarquitosAgent(dry_run=True)
