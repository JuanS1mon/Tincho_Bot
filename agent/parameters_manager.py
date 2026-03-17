"""
agent/parameters_manager.py
============================
Gestiona los parámetros dinámicos del agente.

La IA puede proponer ajustes que se validan, aplican y persisten en MongoDB.
Al reiniciar el agente, los parámetros se restauran desde la DB con los
últimos valores que la IA determinó como óptimos.

Parámetros ajustables:
   - leverage               (1 – 20)
  - max_capital_per_trade  (0.05 – 0.50) — fracción del capital asignado al símbolo
  - risk_per_trade         (0.005 – 0.03)
  - stop_loss              (0.01 – 0.05)
    - take_profit            (0.00 – 0.15, donde 0 = sin límite de ganancia)
  - timeframe              (1m | 3m | 5m | 15m | 30m | 1h | 2h | 4h)
  - analysis_interval_seconds (180 – 3600)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Tuple

from config.settings import settings
from config.agent_config import agent_config
from config.logger import trading_logger as logger, error_logger


def _get_bounds() -> Dict[str, Tuple]:
    """Lee los límites desde agente.md en tiempo de ejecución."""
    return agent_config.param_bounds


def _get_valid_timeframes() -> set:
    """Lee los timeframes válidos desde agente.md en tiempo de ejecución."""
    return agent_config.valid_timeframes


@dataclass
class DynamicParams:
    """
    Parámetros de trading ajustables en tiempo real por la IA.
    Los valores iniciales vienen de .env (via settings) pero la IA los puede cambiar.
    """
    leverage: int                 = field(default_factory=lambda: settings.leverage)
    max_capital_per_trade: float  = field(default_factory=lambda: settings.max_capital_per_trade)
    risk_per_trade: float         = field(default_factory=lambda: settings.risk_per_trade)
    stop_loss: float              = field(default_factory=lambda: settings.stop_loss)
    take_profit: float            = field(default_factory=lambda: settings.take_profit)
    profit_lock_retrace_pct: float = field(default_factory=lambda: settings.profit_lock_retrace_pct)
    timeframe: str                = field(default_factory=lambda: settings.timeframe)
    analysis_interval_seconds: int = field(default_factory=lambda: settings.analysis_interval_seconds)
    sma20_proximity_pct: float    = 0.05   # Máx distancia precio-SMA20 para pullback
    rsi_long_threshold: float     = 40.0   # RSI mínimo para señal LONG
    rsi_short_threshold: float    = 52.0   # RSI máximo para señal SHORT
    liquidation_dominance_ratio: float = 1.5  # Ratio para declarar lado dominante en liquidaciones
    rsi_momentum_boost: float = 8.0    # Reducción del umbral LONG cuando RSI viene subiendo (puntos)
    rsi_overbought: float = 78.0       # RSI máximo para aplicar momentum boost (protege contra sobrecompra)
    tryhard_mode: bool = False         # Relaja filtros de volumen y proximidad para operar más fácil

    # Metadatos de ajustes
    adjustment_count: int         = 0
    last_adjustment_reason: str   = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ParametersManager:
    """
    Singleton que gestiona los parámetros dinámicos del agente.

    Flujo:
      1. Al iniciar: load_from_db() restaura los últimos parámetros de MongoDB.
      2. En cada ciclo: la IA puede proponer ajustes vía apply_adjustments().
      3. Los ajustes se validan contra PARAM_BOUNDS y se escriben en MongoDB.
      4. decision_engine y risk_tool consultan self.params en lugar de settings.
    """

    def __init__(self) -> None:
        self.params = DynamicParams()

    # ── Persistencia ──────────────────────────────────────────────────────────

    def load_from_db(self) -> None:
        """Restaura los últimos parámetros guardados desde MongoDB."""
        try:
            from storage.state_repository import state_repository  # lazy → evitar circular
            saved = state_repository.load_parameters()
            if not saved:
                logger.info("Parámetros dinámicos: usando defaults de .env | %s", self.summary())
                return

            for key, (min_v, max_v, cast) in _get_bounds().items():
                if key in saved:
                    try:
                        val = cast(saved[key])
                        setattr(self.params, key, max(min_v, min(max_v, val)))
                    except (TypeError, ValueError):
                        pass

            if "timeframe" in saved and saved["timeframe"] in _get_valid_timeframes():
                self.params.timeframe = saved["timeframe"]

            self.params.adjustment_count = int(saved.get("adjustment_count", 0))
            self.params.last_adjustment_reason = str(saved.get("last_adjustment_reason", ""))
            logger.info("Parámetros dinámicos restaurados desde DB | %s", self.summary())

        except Exception as exc:
            error_logger.error("ParametersManager.load_from_db error: %s", exc)

    def _persist(self) -> None:
        """Escribe los parámetros actuales en MongoDB."""
        try:
            from storage.state_repository import state_repository
            state_repository.save_parameters(self.params.to_dict())
        except Exception as exc:
            error_logger.error("ParametersManager._persist error: %s", exc)

    # ── Aplicar ajustes de la IA ───────────────────────────────────────────────

    def apply_adjustments(self, adjustments: Dict[str, Any], reason: str = "") -> bool:
        """
        Valida y aplica los ajustes sugeridos por la IA.
        Los valores fuera de límites quedan clampeados, no rechazados.
        Retorna True si se aplicó al menos un cambio real.
        """
        if not adjustments:
            return False

        changes: list[str] = []

        # Timeframe es un string enum especial
        if "timeframe" in adjustments:
            new_tf = str(adjustments["timeframe"])
            if new_tf in _get_valid_timeframes() and new_tf != self.params.timeframe:
                changes.append(f"timeframe: {self.params.timeframe} → {new_tf}")
                self.params.timeframe = new_tf

        # Parámetros numéricos con límites
        for key, (min_v, max_v, cast) in _get_bounds().items():
            if key not in adjustments:
                continue
            try:
                new_val = cast(adjustments[key])
                clamped = max(min_v, min(max_v, new_val))
                old_val = getattr(self.params, key)
                if clamped != old_val:
                    setattr(self.params, key, clamped)
                    changes.append(f"{key}: {old_val} → {clamped}")
            except (TypeError, ValueError) as exc:
                logger.warning("Ajuste inválido para '%s'=%s: %s", key, adjustments[key], exc)

        if changes:
            self.params.adjustment_count += 1
            self.params.last_adjustment_reason = reason[:200]
            logger.info(
                "Parámetros ajustados por IA (#%d) — %s: %s",
                self.params.adjustment_count, reason[:60], " | ".join(changes),
            )
            self._persist()
            return True

        return False

    # ── Helpers ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Resumen compacto de los parámetros actuales."""
        p = self.params
        tp_label = "OFF" if p.take_profit <= 0 else f"{p.take_profit:.1%}"
        return (
            f"leverage={p.leverage}x | max_cap={p.max_capital_per_trade:.0%} | "
            f"SL={p.stop_loss:.1%} TP={tp_label} | PL_retrace={p.profit_lock_retrace_pct:.0%} | "
            f"tf={p.timeframe} | interval={p.analysis_interval_seconds}s | "
            f"ajustes_IA={p.adjustment_count}"
        )


# Singleton global
parameters_manager = ParametersManager()
