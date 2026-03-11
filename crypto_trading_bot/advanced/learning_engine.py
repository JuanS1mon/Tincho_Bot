"""
Advanced - Learning Engine
============================
Motor de aprendizaje simple basado en resultados históricos.
Versión simple: ajusta pesos de indicadores (±0.05) según win/loss.
Los pesos se incluyen como contexto al prompt de IA.

Funcionamiento:
  - Cada indicador tiene un peso inicial de 1.0 (en tabla indicator_weights).
  - Tras cada trade cerrado, se evalúa qué indicadores "acertaron".
  - Si acertó: peso += LEARNING_WEIGHT_ADJUSTMENT (default 0.05).
  - Si falló: peso -= LEARNING_WEIGHT_ADJUSTMENT.
  - Pesos clamped: mínimo 0.1, máximo 2.0.
"""

from typing import Dict, Optional

from config.logger import get_logger
from config.settings import settings
from domain.entities.market_data import MarketSnapshot

logger = get_logger(__name__)


class LearningEngine:
    """
    Motor de aprendizaje simple por pesos de indicadores.
    Evalúa el rendimiento histórico de cada indicador y ajusta su peso.
    """

    def __init__(self, weight_repository=None):
        """
        Args:
            weight_repository: IndicatorWeightRepository para persistir pesos.
        """
        self.weight_repo = weight_repository
        self.adjustment = settings.LEARNING_WEIGHT_ADJUSTMENT

    def get_weights(self) -> Dict[str, float]:
        """
        Obtiene los pesos actuales de todos los indicadores.
        
        Returns:
            Dict {indicator_name: weight}.
        """
        if self.weight_repo:
            return self.weight_repo.get_all_weights()
        # Defaults si no hay repositorio
        return {
            "RSI": 1.0,
            "MACD": 1.0,
            "SMA": 1.0,
            "EMA": 1.0,
            "Volatility": 1.0,
            "Volume": 1.0,
        }

    def evaluate_trade(
        self,
        snapshot_at_entry: MarketSnapshot,
        trade_pnl: float,
    ) -> Dict[str, str]:
        """
        Evalúa un trade completado y ajusta los pesos de los indicadores.
        
        Para cada indicador, determina si su señal al momento de la entrada
        era consistente con el resultado del trade (ganancia o pérdida).
        
        Args:
            snapshot_at_entry: MarketSnapshot al momento de abrir el trade.
            trade_pnl: PnL del trade (positivo = ganancia, negativo = pérdida).
            
        Returns:
            Dict con el ajuste aplicado a cada indicador.
        """
        won = trade_pnl > 0
        adjustments = {}

        # --- RSI ---
        rsi_bullish = snapshot_at_entry.rsi < 50
        rsi_correct = (rsi_bullish and won) or (not rsi_bullish and not won)
        self._update_weight("RSI", rsi_correct)
        adjustments["RSI"] = "+" if rsi_correct else "-"

        # --- MACD ---
        macd_bullish = snapshot_at_entry.macd_signal == "bullish"
        macd_correct = (macd_bullish and won) or (not macd_bullish and not won)
        self._update_weight("MACD", macd_correct)
        adjustments["MACD"] = "+" if macd_correct else "-"

        # --- SMA (trend) ---
        sma_bullish = snapshot_at_entry.trend == "bullish"
        sma_correct = (sma_bullish and won) or (not sma_bullish and not won)
        self._update_weight("SMA", sma_correct)
        adjustments["SMA"] = "+" if sma_correct else "-"

        # --- EMA ---
        ema_bullish = snapshot_at_entry.price > snapshot_at_entry.ema_20
        ema_correct = (ema_bullish and won) or (not ema_bullish and not won)
        self._update_weight("EMA", ema_correct)
        adjustments["EMA"] = "+" if ema_correct else "-"

        # --- Volatility ---
        # Baja volatilidad favorece trades exitosos
        low_vol = snapshot_at_entry.volatility_state != "high"
        vol_correct = (low_vol and won) or (not low_vol and not won)
        self._update_weight("Volatility", vol_correct)
        adjustments["Volatility"] = "+" if vol_correct else "-"

        # --- Volume ---
        vol_increasing = snapshot_at_entry.volume_trend == "increasing"
        vol_trade_correct = (vol_increasing and won) or (not vol_increasing and not won)
        self._update_weight("Volume", vol_trade_correct)
        adjustments["Volume"] = "+" if vol_trade_correct else "-"

        result_emoji = "✅" if won else "❌"
        logger.info(
            f"📚 Learning Engine {result_emoji}: PnL={trade_pnl:.2f} USDT, "
            f"ajustes: {adjustments}"
        )

        return adjustments

    def _update_weight(self, indicator: str, correct: bool) -> None:
        """Actualiza el peso de un indicador en la base de datos."""
        if self.weight_repo:
            self.weight_repo.update_weight(
                indicator, won=correct, adjustment=self.adjustment
            )

    def get_learning_summary(self) -> Dict:
        """
        Genera un resumen del estado del aprendizaje.
        Útil para debugging y para incluir en el prompt de IA.
        """
        weights = self.get_weights()
        stats = []
        if self.weight_repo:
            stats = self.weight_repo.get_stats()

        return {
            "weights": weights,
            "stats": stats,
            "most_reliable": max(weights, key=weights.get) if weights else None,
            "least_reliable": min(weights, key=weights.get) if weights else None,
        }
