# Offline Data Insights Agent

This folder contains a standalone analysis agent that reads MongoDB data and produces recommendations for Tincho1 without modifying the live bot.

## Goal

- Read historical data from MongoDB (`trades`, `market_snapshots`, `agent_states`)
- Compute relevant metrics, averages, and a lightweight short-term forecast
- Generate suggested parameter adjustments for Tincho1
- Never apply changes automatically

## Run

```powershell
python offline_agents/tincho_data_insights_agent.py --hours 72 --symbols BTCUSDT,ETHUSDT
```

## Two Layers (recommended)

Always run the 2-layer flow:

1) Layer 1 (algorithmic): statistics, averages, drawdown, simple prediction.
2) Layer 2 (agentic): LLM reviews layer 1 output and emits two recommendation profiles for Tincho1:
	- Conservative: capital preservation
	- Aggressive: fast gain (higher risk)

```powershell
python offline_agents/tincho_two_layer_agent.py --hours 72 --symbols BTCUSDT,ETHUSDT
```

Output example:

- `reports/tincho_two_layer_report.json`

## Profile Selector (easy mode)

After generating the two-layer report, pick the profile you want and export it:

```powershell
python select_profile.py --profile conservative
python select_profile.py --profile aggressive
```

Requested mapping to Tincho1 modes:

- `python select_profile.py --profile conservative` -> `tryhard`
- `python select_profile.py --profile aggressive` -> `chill`
- `python select_profile.py --interactive` -> `putita`

Interactive selector:

```powershell
python select_profile.py --interactive
```

Default output:

- `reports/tincho_selected_profile.json`

Optional output path:

```powershell
python offline_agents/tincho_data_insights_agent.py --hours 168 --out reports/weekly_insights.json
```

## Output

JSON report example: `reports/tincho_data_insights.json`

Main sections:

- `symbol_stats`: core stats per symbol (win rate, avg pnl, drawdown, long vs short quality)
- `predictions`: simple linear estimate over recent pnl%
- `current_dynamic_params`: current runtime params from DB
- `tincho1_adjustment_brief`: suggested adjustments + rationale
- `layer2_agentic.profiles.conservative`: low-risk recommendation profile
- `layer2_agentic.profiles.aggressive`: fast-gain recommendation profile

## Safety

- Read-only behavior for trading params
- No imports that alter Tincho1 execution loop
- No runtime write-back to `dynamic_parameters`
- Layer 2 is advisory only; no automatic parameter application
