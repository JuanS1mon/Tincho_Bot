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
    recent_trades: Optional[list] = None,    # Últimos trades desde MongoDB
    target_symbol: str = "",                 # símbolo específico a evaluar
    target_direction: str = "",              # dirección específica a evaluar
) -> str:
    """
    Construye el prompt de usuario con todos los datos de mercado, simulación,
    estado del portafolio y parámetros actuales del agente.
    """
    _portfolio = portfolio or portfolio_tool

    # ── Portafolio y métricas de rendimiento ─────────────────────────────────
    # Lista explícita de posiciones abiertas por símbolo
    open_pos_lines = []
    for sym in market_data.keys():
        if _portfolio.has_open_position(sym):
            pos = _portfolio.positions[sym]
            open_pos_lines.append(f"  {sym}: OPEN ({pos.direction}) entry={pos.entry_price:.4f}")
        else:
            open_pos_lines.append(f"  {sym}: NO open position (free to trade)")
    open_pos_detail = "\n".join(open_pos_lines)

    portfolio_block = f"""Portfolio status:
- total_capital:     {_portfolio.capital:.2f} USDT  (grows incrementally with profits)
- available_capital: {_portfolio.available_capital:.2f} USDT  (shared global capital for new trades)
- open_positions:    {len(_portfolio.positions)}
- total_pnl:         {_portfolio.total_pnl:.2f} USDT  ({_portfolio.total_pnl / _portfolio.initial_capital * 100:.1f}% desde inicio)
- win_rate:          {_portfolio.win_rate:.2%}  ({_portfolio.winning_trades}/{_portfolio.total_trades} trades)
Open positions per symbol:
{open_pos_detail}"""

    # ── Parámetros actuales del agente ────────────────────────────────────────
    if dynamic_params is not None:
        p = dynamic_params
        tp_label = "OFF" if p.take_profit <= 0 else f"{p.take_profit:.1%}"
        params_block = f"""
Current agent parameters (AI-adjustable):
- leverage:                  {p.leverage}x         [allowed: 1–25]
- max_capital_per_trade:     {p.max_capital_per_trade:.0%}     [allowed: 5%–70% of symbol allocation]
- risk_per_trade:            {p.risk_per_trade:.3f}    [allowed: 0.005–0.05]
- stop_loss:                 {p.stop_loss:.1%}      [allowed: 1%–8%]
- take_profit:               {tp_label}      [allowed: 0%–30% | 0% = disabled]
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
    available_capital:   {sym_avail:.2f} USDT  (shared capital still free)"""
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

    # ── Historial de trades recientes ───────────────────────────────────────────
    trades_block = ""
    if recent_trades:
        rows = []
        for t in recent_trades[:10]:
            rows.append(
                f"  {t.get('symbol','?')} {t.get('direction','?')} | "
                f"entry={t.get('entry_price',0):.4f} exit={t.get('exit_price',0):.4f} | "
                f"pnl={t.get('pnl',0):+.4f} USDT ({t.get('pnl_pct',0):+.2f}%) | "
                f"{t.get('strategy','?')}"
            )
        trades_block = "\nRecent trade history (newest first):\n" + "\n".join(rows)

    # ── Instrucción de respuesta ──────────────────────────────────────────────
    target_line = ""
    if target_symbol and target_direction:
        target_line = f"""
⚠️  DECISION TARGET: You MUST decide whether to open a {target_direction} trade on {target_symbol}.
    The simulation above is for {target_symbol} {target_direction}. Evaluate ONLY this symbol+direction.
    Set \"symbol\": \"{target_symbol}\" and \"direction\": \"{target_direction}\" in your JSON.
"""

    response_instruction = target_line + """
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
{sim_block}{trades_block}
{response_instruction}"""


def build_market_overview_prompt(
    all_market_data: Dict[str, Dict[str, Any]],
    dynamic_params: Optional[Any],
    portfolio_state: Dict[str, Any],
) -> str:
    """
    Prompt para que Tincho1 evalúe las condiciones globales del mercado
    y sugiera ajustes de parámetros sin necesidad de evaluar un trade específico.
    """
    # Bloque de portafolio
    pnl_pct = portfolio_state["total_pnl"] / max(portfolio_state["initial_capital"], 1) * 100
    port_block = (
        f"Portfolio: capital={portfolio_state['capital']:.2f} USDT | "
        f"pnl={portfolio_state['total_pnl']:+.4f} USDT ({pnl_pct:+.2f}%) | "
        f"win_rate={portfolio_state['win_rate']*100:.1f}% | "
        f"trades={portfolio_state['total_trades']} | "
        f"open_positions={portfolio_state['open_positions']}"
    )

    # Bloque de parámetros actuales
    if dynamic_params is not None:
        p = dynamic_params
        tp_label = "OFF" if p.take_profit <= 0 else f"{p.take_profit:.1%}"
        params_block = (
            f"Current parameters: leverage={p.leverage}x | "
            f"sl={p.stop_loss:.1%} | tp={tp_label} | "
            f"max_cap={p.max_capital_per_trade:.0%} | "
            f"risk={p.risk_per_trade:.1%} | tf={p.timeframe} | "
            f"adjustments_by_AI={p.adjustment_count} | last_reason={p.last_adjustment_reason or 'none'}"
        )
    else:
        params_block = ""

    # Bloque de mercado
    market_lines = []
    for sym, data in all_market_data.items():
        market_lines.append(
            f"{sym}: price={data.get('price', 0):.4f} | trend={data.get('trend', '?')} | "
            f"rsi={data.get('rsi', 0):.1f} | vol={data.get('volume_trend', '?')} | "
            f"oi={data.get('oi_trend', '?')} | funding={data.get('funding_rate', 0)*100:.4f}%"
        )
    market_block = "\n".join(market_lines) if market_lines else "No market data available."

    return f"""MARKET OVERVIEW ANALYSIS — Do NOT evaluate a specific trade.
Your task: assess overall market conditions and suggest parameter adjustments if clearly warranted.

{port_block}
{params_block}

Current market snapshot:
{market_block}

Return ONLY this JSON (no markdown, no explanation):
{{
  "reasoning": "brief market assessment max 120 chars",
  "parameter_adjustments": null or {{
    "leverage": int,
    "max_capital_per_trade": float,
    "stop_loss": float,
    "take_profit": float,
    "timeframe": "string"
  }}
}}
Use null for parameter_adjustments if the market is mixed or no clear adjustment is justified.
Only change parameters if you see STRONG and CLEAR evidence in the data."""
