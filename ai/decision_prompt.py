"""
ai/decision_prompt.py
======================
Construye el prompt que se envía al modelo de lenguaje para:
  1. Decidir si abrir un trade (trade: true/false).
  2. Opcionalmente sugerir ajustes a los parámetros del agente.

El modelo retorna JSON estructurado con ambas partes.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from tools.simulation_tool import SimulationResult
from tools.portfolio_tool import PortfolioTool, portfolio_tool


SYSTEM_PROMPT = """You are a professional quantitative crypto trader specialized in futures markets.
Your role is:
  1. Analyze market data and decide if a futures trade should be opened.
  2. Optionally suggest adjustments to the agent's trading parameters to optimize performance.

Rules:
  - Be conservative — only approve trades with strong confluence of signals.
  - Only suggest parameter adjustments when there is clear evidence they are needed
    (e.g. consistently hitting SL before TP → widen TP or tighten SL).
  - Keep parameter_adjustments null if no changes are warranted.
  - Always respond ONLY with valid JSON. No explanations, no markdown, just raw JSON."""


def build_decision_prompt(
    market_data: Dict[str, Dict[str, Any]],
    simulation: SimulationResult,
    portfolio: Optional[PortfolioTool] = None,
    dynamic_params: Optional[Any] = None,   # DynamicParams desde parameters_manager
) -> str:
    """
    Construye el prompt de usuario con todos los datos de mercado, simulación,
    estado del portafolio y parámetros actuales del agente.
    """
    _portfolio = portfolio or portfolio_tool

    # ── Portafolio y métricas de rendimiento ─────────────────────────────────
    num_symbols = max(1, len(list(market_data.keys())) or 2)
    symbol_alloc = _portfolio.capital / num_symbols

    portfolio_block = f"""Portfolio status:
- total_capital:     {_portfolio.capital:.2f} USDT  (grows incrementally with profits)
- per_symbol_alloc:  {symbol_alloc:.2f} USDT  (capital / {num_symbols} symbols, 50% each)
- open_positions:    {len(_portfolio.positions)}
- total_pnl:         {_portfolio.total_pnl:.2f} USDT  ({_portfolio.total_pnl / _portfolio.initial_capital * 100:.1f}% desde inicio)
- win_rate:          {_portfolio.win_rate:.2%}  ({_portfolio.winning_trades}/{_portfolio.total_trades} trades)"""

    # ── Parámetros actuales del agente ────────────────────────────────────────
    if dynamic_params is not None:
        p = dynamic_params
        params_block = f"""
Current agent parameters (AI-adjustable):
- leverage:                  {p.leverage}x         [allowed: 1–10]
- max_capital_per_trade:     {p.max_capital_per_trade:.0%}     [allowed: 5%–50% of symbol allocation]
- risk_per_trade:            {p.risk_per_trade:.3f}    [allowed: 0.005–0.03]
- stop_loss:                 {p.stop_loss:.1%}      [allowed: 1%–5%]
- take_profit:               {p.take_profit:.1%}      [allowed: 2%–15%]
- timeframe:                 {p.timeframe}         [allowed: 1m|3m|5m|15m|30m|1h|2h|4h]
- analysis_interval_seconds: {p.analysis_interval_seconds}s       [allowed: 180–3600]
- total_parameter_adjustments_by_AI: {p.adjustment_count}
- last_adjustment_reason:    {p.last_adjustment_reason or 'none'}"""
    else:
        params_block = ""

    # ── Datos de mercado por símbolo ──────────────────────────────────────────
    market_blocks = []
    for symbol, data in market_data.items():
        sym_avail = _portfolio.available_capital_for_symbol(symbol)
        block = f"""
{symbol}:
  trend:               {data.get('trend', 'UNKNOWN')}
  price:               {data.get('price', 0):.4f}
  RSI:                 {data.get('rsi', 0):.2f}
  SMA20:               {data.get('sma20', 0):.4f}
  SMA50:               {data.get('sma50', 0):.4f}
  volume_trend:        {data.get('volume_trend', 'UNKNOWN')}
  open_interest_trend: {data.get('oi_trend', 'UNKNOWN')}
  oi_signal:           {data.get('oi_signal', 'NEUTRAL')}
  funding_rate:        {data.get('funding_rate', 0):.4f}
  available_capital:   {sym_avail:.2f} USDT  (from {symbol_alloc:.2f} allocation)"""
        market_blocks.append(block)

    market_section = "\n".join(market_blocks)

    # ── Simulación ────────────────────────────────────────────────────────────
    sim_block = f"""
Simulation result ({simulation.direction}):
  recommendation:    {simulation.recommendation}
  winrate:           {simulation.winrate:.2%}
  expected_profit:   {simulation.expected_profit_pct:.2f}%
  max_drawdown:      {simulation.max_drawdown_pct:.2f}%
  sharpe_ratio:      {simulation.sharpe_ratio:.4f}
  monte_carlo_ruin:  {simulation.mc_ruin_probability:.2%}"""

    # ── Instrucción de respuesta ──────────────────────────────────────────────
    response_instruction = """
Based on ALL data above, decide if a futures trade should be opened AND if any parameters should be adjusted.

Return ONLY this JSON (no markdown, no explanation):
{
  "trade": true or false,
  "symbol": "BTCUSDT or ETHUSDT",
  "direction": "LONG or SHORT",
  "capital_usage": 0.0 to 0.50,
  "confidence": 0.0 to 1.0,
  "reasoning": "brief explanation max 100 chars",
  "parameter_adjustments": null or {
    "leverage": int,
    "max_capital_per_trade": float,
    "stop_loss": float,
    "take_profit": float,
    "timeframe": "string",
    "analysis_interval_seconds": int
  }
}
Note: include in parameter_adjustments ONLY keys you want to change. Use null if no changes needed."""

    return f"""{portfolio_block}
{params_block}

Market data:
{market_section}
{sim_block}
{response_instruction}"""
