"""
tools/risk_tool.py
==================
Valida y calcula los parámetros de riesgo de cada trade:
  - Calcula tamaño de posición (cantidad de contratos)
  - Valida que el capital usado no supere el máximo por trade
  - Calcula precios exactos de Stop Loss y Take Profit
  - Verifica apalancamiento máximo
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from config.settings import settings
from config.logger import trading_logger as logger, error_logger


@dataclass
class RiskParams:
    """Parámetros de riesgo calculados para un trade."""
    is_valid: bool
    rejection_reason: str
    quantity: float          # cantidad en contratos/monedas
    capital_to_use: float    # USDT a utilizar
    entry_price: float       # precio de entrada real
    stop_loss_price: float
    take_profit_price: float
    trailing_callback_pct: float
    risk_reward_ratio: float


class RiskTool:
    """Calcula y valida parámetros de riesgo antes de ejecutar un trade."""

    def __init__(self) -> None:
        self.max_capital_pct = settings.max_capital_per_trade
        self.risk_per_trade = settings.risk_per_trade
        self.stop_loss_pct = settings.stop_loss
        self.take_profit_pct = settings.take_profit
        self.max_leverage = settings.leverage
        self.trailing_callback_pct = 1.0  # 1% trailing stop por defecto

    def sync_params(self, params) -> None:
        """
        Sincroniza los parámetros con los valores dinámicos del agente.
        Se llama desde decision_engine antes de cada validación.
        """
        self.max_capital_pct = params.max_capital_per_trade
        self.risk_per_trade = params.risk_per_trade
        self.stop_loss_pct = params.stop_loss
        self.take_profit_pct = params.take_profit
        self.max_leverage = params.leverage

    def validate(
        self,
        direction: str,
        entry_price: float,
        available_capital: float,
        total_capital: float,
        capital_usage: float = 0.0,   # sugerido por IA (0.0 = usar default)
    ) -> RiskParams:
        """
        Evalúa si el trade es válido y calcula todos los parámetros de riesgo.
        
        direction: 'LONG' o 'SHORT'
        entry_price: precio de entrada estimado
        available_capital: USDT disponibles
        total_capital: USDT totales del portafolio
        capital_usage: fracción sugerida por la IA (ej. 0.25)
        """
        # ── Validar capital disponible ────────────────────────────────────────
        if available_capital <= 0:
            return self._reject("Capital disponible insuficiente (≤ 0)")

        if available_capital < 10:  # mínimo operativo
            return self._reject(f"Capital disponible muy bajo: {available_capital:.2f} USDT (mínimo 10)")

        # ── Calcular capital a usar ────────────────────────────────────────────
        # Respetar el máximo por trade y la sugerencia de la IA
        max_capital = total_capital * self.max_capital_pct
        if capital_usage > 0:
            intended = total_capital * min(capital_usage, self.max_capital_pct)
        else:
            intended = total_capital * self.max_capital_pct

        capital_to_use = min(intended, available_capital, max_capital)

        if capital_to_use <= 0:
            return self._reject("Capital calculado es 0 o negativo")

        # ── Calcular cantidad (qty) ────────────────────────────────────────────
        # qty = (capital * leverage) / entry_price
        notional = capital_to_use * self.max_leverage
        quantity = notional / entry_price if entry_price > 0 else 0

        if quantity <= 0:
            return self._reject("Cantidad calculada inválida (≤ 0)")

        # ── Calcular SL / TP ──────────────────────────────────────────────────
        sl_price, tp_price = self._calc_sl_tp(direction, entry_price)

        # ── Risk/Reward mínimo: 1:2 ───────────────────────────────────────────
        risk = abs(entry_price - sl_price)
        reward = abs(tp_price - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        if rr_ratio < 2.0:
            return self._reject(f"Risk/Reward ratio insuficiente: {rr_ratio:.2f} (mínimo 2.0)")

        logger.debug(
            "Riesgo validado: dir=%s price=%.2f qty=%.4f capital=%.2f SL=%.2f TP=%.2f RR=%.2f",
            direction, entry_price, quantity, capital_to_use, sl_price, tp_price, rr_ratio,
        )

        return RiskParams(
            is_valid=True,
            rejection_reason="",
            quantity=round(quantity, 4),
            capital_to_use=round(capital_to_use, 2),
            entry_price=round(entry_price, 6),
            stop_loss_price=round(sl_price, 4),
            take_profit_price=round(tp_price, 4),
            trailing_callback_pct=self.trailing_callback_pct,
            risk_reward_ratio=round(rr_ratio, 2),
        )

    def _calc_sl_tp(self, direction: str, entry_price: float) -> Tuple[float, float]:
        """Calcula precios de Stop Loss y Take Profit."""
        if direction == "LONG":
            sl = entry_price * (1 - self.stop_loss_pct)
            tp = entry_price * (1 + self.take_profit_pct)
        else:  # SHORT
            sl = entry_price * (1 + self.stop_loss_pct)
            tp = entry_price * (1 - self.take_profit_pct)
        return sl, tp

    @staticmethod
    def _reject(reason: str) -> RiskParams:
        logger.debug("Trade rechazado por riesgo: %s", reason)
        return RiskParams(
            is_valid=False,
            rejection_reason=reason,
            quantity=0,
            capital_to_use=0,
            stop_loss_price=0,
            entry_price=0.0,
            take_profit_price=0,
            trailing_callback_pct=0,
            risk_reward_ratio=0,
        )


# Instancia global
risk_tool = RiskTool()
