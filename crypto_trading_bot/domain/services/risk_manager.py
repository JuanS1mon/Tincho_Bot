"""
Domain Service - Risk Manager
==============================
Valida condiciones de riesgo antes de ejecutar operaciones.
Cancela si falla cualquier condición:
  - capital_usage <= MAX_CAPITAL_USAGE
  - trade_size <= MAX_CAPITAL_PER_TRADE  
  - daily_loss < DAILY_MAX_LOSS
  - Si hay flag de manipulación → reduce exposición o cancela.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from config.logger import get_logger
from config.settings import settings
from domain.entities.portfolio import Portfolio
from domain.entities.trade_signal import TradeSignal

logger = get_logger(__name__)


@dataclass
class RiskValidation:
    """Resultado de la validación de riesgo."""
    approved: bool
    adjusted_capital_usage: float
    reason: str
    warnings: list


class RiskManager:
    """
    Gestor de riesgo del bot de trading.
    Valida todas las condiciones de riesgo antes de permitir operaciones.
    """

    def __init__(self):
        self.max_capital_usage = settings.MAX_CAPITAL_USAGE
        self.max_capital_per_trade = settings.MAX_CAPITAL_PER_TRADE
        self.daily_max_loss = settings.DAILY_MAX_LOSS
        self.stop_loss = settings.STOP_LOSS
        self.take_profit = settings.TAKE_PROFIT

    def validate(
        self,
        signal: TradeSignal,
        portfolio: Portfolio,
        prices: Dict[str, float],
        manipulation_detected: bool = False,
    ) -> RiskValidation:
        """
        Valida una señal de trading contra todas las reglas de riesgo.
        
        Args:
            signal: Señal de trading de la IA.
            portfolio: Estado actual del portafolio.
            prices: Precios actuales de mercado.
            manipulation_detected: Si se detectó manipulación de mercado.
            
        Returns:
            RiskValidation con el resultado de la validación.
        """
        warnings = []
        capital = portfolio.capital_actual(prices)

        # --- Condición 1: No invertir si la señal dice que no ---
        if not signal.invest:
            return RiskValidation(
                approved=False,
                adjusted_capital_usage=0.0,
                reason="La IA decidió no invertir",
                warnings=[],
            )

        # --- Condición 2: Confianza mínima ---
        if signal.confidence < 0.5:
            return RiskValidation(
                approved=False,
                adjusted_capital_usage=0.0,
                reason=f"Confianza insuficiente: {signal.confidence:.2f} < 0.50",
                warnings=[],
            )

        # --- Condición 3: Pérdida diaria máxima ---
        daily_loss = portfolio.daily_loss_percent(prices)
        if daily_loss >= self.daily_max_loss:
            return RiskValidation(
                approved=False,
                adjusted_capital_usage=0.0,
                reason=(
                    f"Pérdida diaria máxima alcanzada: "
                    f"{daily_loss:.2%} >= {self.daily_max_loss:.2%}"
                ),
                warnings=[],
            )

        # --- Condición 4: Uso máximo de capital ---
        adjusted_usage = min(signal.capital_usage, self.max_capital_usage)
        if signal.capital_usage > self.max_capital_usage:
            warnings.append(
                f"Capital usage reducido: {signal.capital_usage:.2f} → {adjusted_usage:.2f}"
            )

        # --- Condición 5: Manipulación detectada ---
        if manipulation_detected:
            # Reducir exposición un 50%
            adjusted_usage *= 0.5
            warnings.append(
                f"⚠️ Manipulación detectada: exposición reducida 50% → {adjusted_usage:.2f}"
            )

            # Si después de reducir queda muy poco, cancelar
            if adjusted_usage < 0.1:
                return RiskValidation(
                    approved=False,
                    adjusted_capital_usage=0.0,
                    reason="Manipulación detectada y exposición resultante demasiado baja",
                    warnings=warnings,
                )

        # --- Condición 6: Validar tamaño por trade individual ---
        for asset, alloc_pct in signal.allocation.items():
            trade_pct = adjusted_usage * alloc_pct
            if trade_pct > self.max_capital_per_trade:
                old_pct = trade_pct
                # Ajustar proporcionalmente
                adjusted_usage = self.max_capital_per_trade / alloc_pct
                warnings.append(
                    f"Trade {asset} excede max_per_trade: {old_pct:.2f} → ajustado"
                )

        # --- Condición 7: Capital mínimo viable ---
        trade_amount = capital * adjusted_usage
        if trade_amount < 10.0:  # Mínimo 10 USDT para operar
            return RiskValidation(
                approved=False,
                adjusted_capital_usage=0.0,
                reason=f"Capital insuficiente para operar: {trade_amount:.2f} USDT < 10 USDT",
                warnings=warnings,
            )

        # --- Aprobado ---
        if warnings:
            for w in warnings:
                logger.warning(f"RiskManager: {w}")

        logger.info(
            f"RiskManager APROBADO: capital={capital:.2f}, "
            f"usage={adjusted_usage:.2f}, amount={trade_amount:.2f} USDT"
        )

        return RiskValidation(
            approved=True,
            adjusted_capital_usage=adjusted_usage,
            reason="Todas las condiciones de riesgo superadas",
            warnings=warnings,
        )

    def calculate_stop_take(
        self, entry_price: float
    ) -> Tuple[float, float]:
        """
        Calcula los niveles de stop-loss y take-profit.
        
        Returns:
            Tuple (stop_loss_price, take_profit_price)
        """
        sl_price = entry_price * (1 - self.stop_loss)
        tp_price = entry_price * (1 + self.take_profit)
        return round(sl_price, 2), round(tp_price, 2)
