"""
Infrastructure - AI Prompt Builder
=====================================
Construye los prompts para la IA de trading.
  - System prompt: rol fijo de analista cuantitativo.
  - User prompt: resumen estadístico dinámico del mercado.
Incluye datos avanzados: order book, alertas whale, perfil de aprendizaje.
"""

from typing import Dict, List, Optional

from config.logger import get_logger
from domain.entities.market_data import MarketSnapshot

logger = get_logger("ai")

# ============================================================
# SYSTEM PROMPT FIJO
# ============================================================
SYSTEM_PROMPT = """You are a quantitative crypto trading analyst.

Your task is to allocate capital between BTC and ETH using statistical market information.

Your priorities are:

1. Capital preservation
2. Probabilistic advantage
3. Risk control

Rules:

- Never allocate more capital than allowed.
- Avoid trading when signals are unclear.
- Prefer stronger trends.
- Account for volatility risk.
- If whale activity suggests manipulation, reduce exposure.
- Consider order book imbalance for entry timing.
- Weight indicators by their historical reliability (provided in indicator_weights).

Return JSON only with this exact schema:
{
  "invest": true/false,
  "confidence": 0.0-1.0,
  "capital_usage": 0.0-1.0,
  "allocation": {"BTC": 0.0-1.0, "ETH": 0.0-1.0},
  "market_state": "bullish/bearish/sideways/high_volatility",
  "reasoning": "brief explanation"
}

IMPORTANT: allocation values must sum to 1.0 if invest is true.
If invest is false, set capital_usage to 0 and allocation to {"BTC": 0, "ETH": 0}."""


class AIPromptBuilder:
    """Construye prompts dinámicos para el motor de IA."""

    def build_system_prompt(self) -> str:
        """Retorna el system prompt fijo."""
        return SYSTEM_PROMPT

    def build_user_prompt(
        self,
        capital: float,
        max_capital_usage: float,
        snapshots: Dict[str, MarketSnapshot],
        orderbook_analysis: Optional[Dict[str, dict]] = None,
        whale_alerts: Optional[List[dict]] = None,
        manipulation_flags: Optional[Dict[str, bool]] = None,
        indicator_weights: Optional[Dict[str, float]] = None,
        simulation_results: Optional[dict] = None,
    ) -> str:
        """
        Construye el user prompt con datos estadísticos del mercado.
        
        Args:
            capital: Capital disponible en USDT.
            max_capital_usage: Porcentaje máximo de capital a usar.
            snapshots: Diccionario de MarketSnapshot por símbolo.
            orderbook_analysis: Análisis del order book por símbolo.
            whale_alerts: Lista de alertas de ballenas detectadas.
            manipulation_flags: Flags de manipulación por símbolo.
            indicator_weights: Pesos aprendidos por indicador.
            simulation_results: Resultados de backtesting/Monte Carlo.
        """
        lines = []

        # --- Capital ---
        lines.append(f"Capital available: {capital:.2f} USDT")
        lines.append(f"Maximum capital usage: {max_capital_usage:.0%}")
        lines.append("")

        # --- Datos de mercado por símbolo ---
        lines.append(f"Market statistics from last 30 days:")
        lines.append("")

        for symbol, snapshot in snapshots.items():
            asset = symbol.replace("USDT", "")
            lines.append(f"{asset}:")
            lines.append(f"  price: {snapshot.price:.2f}")
            lines.append(f"  trend: {snapshot.trend}")
            lines.append(f"  momentum: {snapshot.momentum}")
            lines.append(f"  RSI: {snapshot.rsi:.1f}")
            lines.append(f"  MACD: {snapshot.macd_signal}")
            lines.append(f"  SMA20: {snapshot.sma_20:.2f}")
            lines.append(f"  SMA50: {snapshot.sma_50:.2f}")
            lines.append(f"  EMA20: {snapshot.ema_20:.2f}")
            lines.append(f"  volatility: {snapshot.volatility:.2f}%")
            lines.append(f"  volatility_state: {snapshot.volatility_state}")
            lines.append(f"  volume_trend: {snapshot.volume_trend}")
            lines.append(f"  market_state: {snapshot.market_state}")
            lines.append("")

        # --- Order Book Analysis ---
        if orderbook_analysis:
            lines.append("Order Book Analysis:")
            for symbol, analysis in orderbook_analysis.items():
                asset = symbol.replace("USDT", "")
                lines.append(f"  {asset}:")
                lines.append(f"    bid_ask_spread: {analysis.get('spread', 'N/A')}")
                lines.append(f"    imbalance_ratio: {analysis.get('imbalance_ratio', 'N/A')}")
                lines.append(f"    buy_pressure: {analysis.get('buy_pressure', 'N/A')}")
                lines.append(f"    support_walls: {analysis.get('support_walls', 'N/A')}")
                lines.append(f"    resistance_walls: {analysis.get('resistance_walls', 'N/A')}")
            lines.append("")

        # --- Whale Alerts ---
        if whale_alerts:
            lines.append("⚠️ Whale Activity Detected:")
            for alert in whale_alerts[-5:]:  # Últimas 5 alertas
                lines.append(
                    f"  - {alert.get('symbol', '?')}: "
                    f"{alert.get('type', '?')} "
                    f"qty={alert.get('quantity', 0):.4f} "
                    f"@ {alert.get('price', 0):.2f}"
                )
            lines.append("")

        # --- Manipulation Flags ---
        if manipulation_flags:
            lines.append("Manipulation Detection:")
            for symbol, detected in manipulation_flags.items():
                asset = symbol.replace("USDT", "")
                status = "⚠️ DETECTED" if detected else "✅ Clear"
                lines.append(f"  {asset}: {status}")
            lines.append("")

        # --- Indicator Weights (aprendizaje) ---
        if indicator_weights:
            lines.append("Indicator reliability weights (from historical performance):")
            for indicator, weight in indicator_weights.items():
                lines.append(f"  {indicator}: {weight:.2f}")
            lines.append("")

        # --- Simulation Results ---
        if simulation_results:
            lines.append("Simulation Results:")
            lines.append(f"  backtest_win_rate: {simulation_results.get('win_rate', 'N/A')}")
            lines.append(f"  backtest_profit: {simulation_results.get('profit', 'N/A')}")
            lines.append(f"  backtest_sharpe: {simulation_results.get('sharpe_ratio', 'N/A')}")
            lines.append(f"  monte_carlo_median_return: {simulation_results.get('mc_median_return', 'N/A')}")
            lines.append(f"  monte_carlo_risk_of_ruin: {simulation_results.get('mc_risk_of_ruin', 'N/A')}")
            lines.append("")

        prompt = "\n".join(lines)
        logger.info(f"User prompt construido ({len(prompt)} chars)")
        logger.debug(f"User prompt:\n{prompt}")

        return prompt
