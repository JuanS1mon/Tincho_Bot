"""
ai/decision_prompt.py
======================
Construye el prompt que se envía al modelo de lenguaje para validar
una decisión de trading. El modelo retorna JSON estructurado.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from tools.indicator_tool import Indicators
from tools.simulation_tool import SimulationResult
from tools.portfolio_tool import PortfolioTool, portfolio_tool
from analysis.trend_detector import TrendDetector, trend_detector


SYSTEM_PROMPT = """You are a professional quantitative crypto trader specialized in futures markets.
Your role is to analyze market data and decide if a futures trade should be opened.
You must be conservative — only approve trades with strong confluence of signals.
Always respond ONLY with valid JSON. No explanations, no markdown, just raw JSON."""


def build_decision_prompt(
    market_data: Dict[str, Dict[str, Any]],
    simulation: SimulationResult,
    portfolio: Optional[PortfolioTool] = None,
) -> str:
    """
    Construye el prompt de usuario con todos los datos de mercado y simulación.
    
    market_data: dict de {symbol: {trend, price, rsi, sma20, sma50, volume_trend, oi, funding}}
    simulation: resultado de SimulationTool
    portfolio: instancia de PortfolioTool para el estado del portafolio
    """
    _portfolio = portfolio or portfolio_tool

    # ── Portafolio ────────────────────────────────────────────────────────────
    portfolio_block = f"""Portfolio status:
- total_capital: {_portfolio.capital:.2f} USDT
- available_capital: {_portfolio.available_capital:.2f} USDT
- open_positions: {len(_portfolio.positions)}
- win_rate: {_portfolio.win_rate:.2%}"""

    # ── Datos de mercado por símbolo ──────────────────────────────────────────
    market_blocks = []
    for symbol, data in market_data.items():
        block = f"""
{symbol}:
  trend: {data.get('trend', 'UNKNOWN')}
  price: {data.get('price', 0):.4f}
  RSI: {data.get('rsi', 0):.2f}
  SMA20: {data.get('sma20', 0):.4f}
  SMA50: {data.get('sma50', 0):.4f}
  volume_trend: {data.get('volume_trend', 'UNKNOWN')}
  open_interest_trend: {data.get('oi_trend', 'UNKNOWN')}
  funding_rate: {data.get('funding_rate', 0):.4f}
  oi_signal: {data.get('oi_signal', 'NEUTRAL')}"""
        market_blocks.append(block)

    market_section = "\n".join(market_blocks)

    # ── Simulación ────────────────────────────────────────────────────────────
    sim_block = f"""
Simulation result ({simulation.direction}):
  recommendation: {simulation.recommendation}
  winrate: {simulation.winrate:.2%}
  expected_profit: {simulation.expected_profit_pct:.2f}%
  max_drawdown: {simulation.max_drawdown_pct:.2f}%
  sharpe_ratio: {simulation.sharpe_ratio:.4f}
  monte_carlo_ruin_prob: {simulation.mc_ruin_probability:.2%}"""

    # ── Instrucción de respuesta ──────────────────────────────────────────────
    response_instruction = """
Based on ALL the data above, decide if a futures trade should be opened.
Consider: trend alignment, RSI levels, volume confirmation, OI trend, funding rate sentiment, simulation quality.

Return ONLY this JSON (no markdown, no explanation):
{
  "trade": true or false,
  "symbol": "BTCUSDT or ETHUSDT",
  "direction": "LONG or SHORT",
  "capital_usage": 0.0 to 0.30,
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation max 100 chars"
}"""

    return f"""{portfolio_block}

Market data:
{market_section}
{sim_block}
{response_instruction}"""
