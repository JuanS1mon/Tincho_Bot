"""
agent/marquitos_brain.py
=========================
Cerebro de Marquitos — Aprendizaje por refuerzo simple (RL sin frameworks).

Qué aprende:
  - Qué SÍMBOLOS son más rentables (scores por EMA de resultados)
  - MOMENTUM mínimo óptimo para entrar
  - RSI máximo óptimo para entrar
  - TAKE PROFIT óptimo (más agresivo en rachas ganadoras, conservador en pérdidas)

Cómo aprende:
  - WIN  (+reward): refuerza las condiciones que llevaron a la ganancia.
  - LOSS (-castigo): penaliza las condiciones que llevaron a la pérdida.
  - Una "pérdida" se activa cuando la posición expira por timeout (MAX_HOLD_SECONDS)
    sin haber llegado al TP. El PnL real al cierre puede ser positivo, negativo o 0.

Persistencia:
  - data/marquitos_brain.json — sobrevive reinicios.
  - Si el archivo no existe (primera vez), arranca con valores por defecto.

Fórmulas:
  symbol_score(t+1) = α * outcome ± (1-α) * score(t)   [outcome: +1 win / -1 loss]
  parámetros:  ajuste proporcional al tamaño de la recompensa
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.logger import trading_logger as logger, error_logger

# ── Ruta de persistencia ──────────────────────────────────────────────────────
_BRAIN_FILE = Path(__file__).parent.parent / "data" / "marquitos_brain.json"

# ── Hiperparámetros de aprendizaje ────────────────────────────────────────────
_EMA_ALPHA: float = 0.30          # peso de la experiencia nueva sobre el score de símbolo
_MAX_HISTORY: int = 100           # trades a recordar
_MAX_HOLD_SECONDS: int = 300      # 5 minutos: si no llegó al TP → "pérdida" y aprende

# ── Límites de parámetros adaptativos ────────────────────────────────────────
_BOUNDS = {
    "momentum_threshold": (0.0010, 0.0150),   # 0.1% – 1.5%
    "rsi_max":            (55.0,   82.0),
    "take_profit":        (0.0040, 0.0250),    # 0.4% – 2.5%
}

# ── Tasas de ajuste por evento ────────────────────────────────────────────────
_WIN_MOMENTUM_DECAY:  float = 0.97    # baja la barrera de entrada si gana
_LOSS_MOMENTUM_RAISE: float = 1.05   # sube la barrera si pierde
_WIN_RSI_BUMP:        float = 0.5    # +0.5 al RSI max si gana
_LOSS_RSI_SHRINK:     float = 1.0    # -1.0 al RSI max si pierde
_WIN_TP_STREAK_BUMP:  float = 1.05   # TP +5% cada 3 wins consecutivos
_LOSS_TP_DECAY:       float = 0.95   # TP -5% si pierde


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class MarquitosBrain:
    """
    Motor de aprendizaje por refuerzo de Marquitos.
    Thread-safe (solo lo escribe el hilo de Marquitos).
    """

    def __init__(self) -> None:
        # ── Parámetros adaptativos actuales ───────────────────────────────────
        self.momentum_threshold: float = 0.003    # 0.3%
        self.rsi_max: float = 72.0
        self.take_profit: float = 0.008           # 0.8%

        # ── Scores por símbolo (-1 = pésimo, 0 = neutro, +1 = excelente) ─────
        self.symbol_scores: Dict[str, float] = {}

        # ── Rachas y métricas ─────────────────────────────────────────────────
        self.win_streak: int = 0
        self.loss_streak: int = 0
        self.total_reward: float = 0.0
        self.trades_learned: int = 0

        # ── Historial de experiencias ─────────────────────────────────────────
        # Cada entry: {symbol, momentum, rsi, outcome, reward, pnl_pct, hold_secs, ts}
        self.history: List[Dict[str, Any]] = []

        self._load()

    # ── Máximo tiempo de espera ───────────────────────────────────────────────

    @property
    def max_hold_seconds(self) -> int:
        return _MAX_HOLD_SECONDS

    # ── API pública ───────────────────────────────────────────────────────────

    def on_win(
        self,
        symbol: str,
        momentum: float,
        rsi: Optional[float],
        pnl_pct: float,
        hold_secs: float,
    ) -> None:
        """
        Llamar cuando un trade cierra con ganancia (llegó al TP).
        reward proporcional al pnl_pct.
        """
        reward = pnl_pct  # positivo, ej. 0.008 para +0.8%
        self.total_reward += reward
        self.win_streak += 1
        self.loss_streak = 0
        self.trades_learned += 1

        # Actualizar score del símbolo
        self._update_symbol_score(symbol, outcome=+1.0)

        # Ajustar momentum threshold: si entró con momentum bajo y ganó → bajar barrera
        if momentum < self.momentum_threshold * 1.5:
            self.momentum_threshold = _clamp(
                self.momentum_threshold * _WIN_MOMENTUM_DECAY,
                *_BOUNDS["momentum_threshold"],
            )

        # Ajustar RSI: si ganó sin que el RSI fuera un problema → relajar un poco
        if rsi is not None and rsi < self.rsi_max - 5:
            self.rsi_max = _clamp(self.rsi_max + _WIN_RSI_BUMP, *_BOUNDS["rsi_max"])

        # Ajustar TP: cada 3 wins consecutivos → ser más ambicioso
        if self.win_streak % 3 == 0:
            self.take_profit = _clamp(
                self.take_profit * _WIN_TP_STREAK_BUMP,
                *_BOUNDS["take_profit"],
            )

        self._record(symbol, momentum, rsi, "WIN", reward, pnl_pct, hold_secs)
        self._log_state("WIN", symbol, reward)
        self._save()

    def on_loss(
        self,
        symbol: str,
        momentum: float,
        rsi: Optional[float],
        pnl_pct: float,
        hold_secs: float,
    ) -> None:
        """
        Llamar cuando un trade cierra por timeout sin ganar (o con PnL negativo).
        El castigo es proporcional al tamaño de la pérdida (o al tiempo desperdiciado).
        """
        # Si salió flat o con ligera ganancia, castigo leve; si perdió, castigo mayor
        penalty = abs(pnl_pct) if pnl_pct < 0 else 0.001  # mínimo 0.1% de castigo
        reward = -penalty
        self.total_reward += reward
        self.loss_streak += 1
        self.win_streak = 0
        self.trades_learned += 1

        # Penalizar el símbolo
        self._update_symbol_score(symbol, outcome=-1.0)

        # Raise momentum threshold: hay que ser más selectivo
        self.momentum_threshold = _clamp(
            self.momentum_threshold * _LOSS_MOMENTUM_RAISE,
            *_BOUNDS["momentum_threshold"],
        )

        # Bajar RSI máximo: ser más estricto con sobrecompra
        if rsi is not None:
            self.rsi_max = _clamp(self.rsi_max - _LOSS_RSI_SHRINK, *_BOUNDS["rsi_max"])

        # TP más conservador: tomar ganancias más rápido
        self.take_profit = _clamp(
            self.take_profit * _LOSS_TP_DECAY,
            *_BOUNDS["take_profit"],
        )

        self._record(symbol, momentum, rsi, "LOSS", reward, pnl_pct, hold_secs)
        self._log_state("LOSS", symbol, reward)
        self._save()

    def get_symbol_priority(self, symbols: List[str]) -> List[str]:
        """
        Ordena los símbolos de mayor a menor score aprendido.
        Símbolos sin historial quedan en score 0 (neutral).
        """
        return sorted(symbols, key=lambda s: self.symbol_scores.get(s, 0.0), reverse=True)

    def report(self) -> str:
        """Resumen del estado aprendido (para logs)."""
        top = sorted(self.symbol_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        top_str = " | ".join(f"{s}={v:+.2f}" for s, v in top) if top else "sin datos"
        return (
            f"trades={self.trades_learned} | reward={self.total_reward:+.4f} | "
            f"streak=W{self.win_streak}/L{self.loss_streak} | "
            f"momentum={self.momentum_threshold*100:.2f}% | "
            f"rsi_max={self.rsi_max:.1f} | "
            f"tp={self.take_profit*100:.2f}% | "
            f"top_syms=[{top_str}]"
        )

    # ── Internos ──────────────────────────────────────────────────────────────

    def _update_symbol_score(self, symbol: str, outcome: float) -> None:
        old = self.symbol_scores.get(symbol, 0.0)
        self.symbol_scores[symbol] = _EMA_ALPHA * outcome + (1 - _EMA_ALPHA) * old

    def _record(
        self,
        symbol: str,
        momentum: float,
        rsi: Optional[float],
        outcome: str,
        reward: float,
        pnl_pct: float,
        hold_secs: float,
    ) -> None:
        self.history.append({
            "ts": time.time(),
            "symbol": symbol,
            "momentum": round(momentum, 6),
            "rsi": round(rsi, 1) if rsi else None,
            "outcome": outcome,
            "reward": round(reward, 6),
            "pnl_pct": round(pnl_pct, 6),
            "hold_secs": round(hold_secs, 1),
        })
        if len(self.history) > _MAX_HISTORY:
            self.history = self.history[-_MAX_HISTORY:]

    def _log_state(self, outcome: str, symbol: str, reward: float) -> None:
        icon = "🧠✅" if outcome == "WIN" else "🧠❌"
        logger.info(
            "%s Marquitos aprendió [%s] %s | reward=%+.4f | %s",
            icon,
            outcome,
            symbol,
            reward,
            self.report(),
        )

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            _BRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "momentum_threshold": self.momentum_threshold,
                "rsi_max": self.rsi_max,
                "take_profit": self.take_profit,
                "symbol_scores": self.symbol_scores,
                "win_streak": self.win_streak,
                "loss_streak": self.loss_streak,
                "total_reward": self.total_reward,
                "trades_learned": self.trades_learned,
                "history": self.history[-20:],   # solo últimos 20 en disco
                "saved_at": time.time(),
            }
            _BRAIN_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            error_logger.error("🧠 [Marquitos] Error guardando cerebro: %s", exc)

    def _load(self) -> None:
        if not _BRAIN_FILE.exists():
            logger.info("🧠 [Marquitos] Cerebro nuevo — partiendo desde cero")
            return
        try:
            data = json.loads(_BRAIN_FILE.read_text(encoding="utf-8"))
            self.momentum_threshold = _clamp(
                float(data.get("momentum_threshold", self.momentum_threshold)),
                *_BOUNDS["momentum_threshold"],
            )
            self.rsi_max = _clamp(
                float(data.get("rsi_max", self.rsi_max)),
                *_BOUNDS["rsi_max"],
            )
            self.take_profit = _clamp(
                float(data.get("take_profit", self.take_profit)),
                *_BOUNDS["take_profit"],
            )
            self.symbol_scores = {
                k: float(v) for k, v in data.get("symbol_scores", {}).items()
            }
            self.win_streak = int(data.get("win_streak", 0))
            self.loss_streak = int(data.get("loss_streak", 0))
            self.total_reward = float(data.get("total_reward", 0.0))
            self.trades_learned = int(data.get("trades_learned", 0))
            self.history = list(data.get("history", []))
            logger.info(
                "🧠 [Marquitos] Cerebro cargado — %s",
                self.report(),
            )
        except Exception as exc:
            error_logger.error("🧠 [Marquitos] Error cargando cerebro: %s", exc)


# Instancia global
marquitos_brain = MarquitosBrain()
