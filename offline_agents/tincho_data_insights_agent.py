from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from pymongo import MongoClient

# Ensure project root is on path when running this file directly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.agent_config import agent_config
from config.settings import settings


@dataclass
class SymbolStats:
    symbol: str
    total_trades: int
    win_rate: float
    avg_pnl: float
    avg_pnl_pct: float
    total_pnl: float
    profit_factor: float
    max_drawdown_pct: float
    long_win_rate: float
    short_win_rate: float


class TinchoDataInsightsAgent:
    """
    Standalone analysis agent:
    - Reads historical data from MongoDB
    - Computes relevant metrics and lightweight predictions
    - Produces parameter suggestions for Tincho1

    This agent NEVER writes parameters and does not modify runtime behavior.
    """

    def __init__(self, mongo_uri: str, db_name: str) -> None:
        self._client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        self._db = self._client[db_name]

    def close(self) -> None:
        self._client.close()

    def _load_trades(self, since_hours: int) -> List[Dict[str, Any]]:
        since_dt = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        return list(
            self._db["trades"]
            .find({"timestamp": {"$gte": since_dt}}, {"_id": 0})
            .sort("timestamp", 1)
        )

    def _load_market_snapshots(self, symbol: str, limit: int = 300) -> List[Dict[str, Any]]:
        return list(
            self._db["market_snapshots"]
            .find({"symbol": symbol}, {"_id": 0})
            .sort("timestamp", -1)
            .limit(limit)
        )

    @staticmethod
    def _safe_ratio(num: float, den: float) -> float:
        return (num / den) if den else 0.0

    @staticmethod
    def _max_drawdown_pct(pnls: List[float], baseline_equity: float = 100.0) -> float:
        if not pnls:
            return 0.0
        curve = baseline_equity + np.cumsum(np.array(pnls, dtype=float))
        peaks = np.maximum.accumulate(curve)
        dd = (peaks - curve) / np.maximum(peaks, 1e-9)
        return float(np.max(dd)) if len(dd) else 0.0

    @staticmethod
    def _clamp_param(name: str, value: float) -> float:
        bounds = agent_config.param_bounds.get(name)
        if not bounds:
            return value
        min_v, max_v, _cast = bounds
        return max(min_v, min(max_v, value))

    def _build_symbol_stats(self, symbol: str, trades: List[Dict[str, Any]]) -> SymbolStats:
        sym = [t for t in trades if t.get("symbol") == symbol]
        if not sym:
            return SymbolStats(symbol, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        pnls = [float(t.get("pnl", 0.0) or 0.0) for t in sym]
        pnl_pcts = [float(t.get("pnl_pct", 0.0) or 0.0) for t in sym]

        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        long_trades = [t for t in sym if t.get("direction") == "LONG"]
        short_trades = [t for t in sym if t.get("direction") == "SHORT"]

        long_win_rate = self._safe_ratio(
            sum(1 for t in long_trades if float(t.get("pnl", 0.0) or 0.0) > 0),
            len(long_trades),
        )
        short_win_rate = self._safe_ratio(
            sum(1 for t in short_trades if float(t.get("pnl", 0.0) or 0.0) > 0),
            len(short_trades),
        )

        return SymbolStats(
            symbol=symbol,
            total_trades=len(sym),
            win_rate=self._safe_ratio(len(wins), len(sym)),
            avg_pnl=float(np.mean(pnls)) if pnls else 0.0,
            avg_pnl_pct=float(np.mean(pnl_pcts)) if pnl_pcts else 0.0,
            total_pnl=float(np.sum(pnls)),
            profit_factor=self._safe_ratio(float(np.sum(wins)), float(np.sum(losses))),
            max_drawdown_pct=self._max_drawdown_pct(pnls),
            long_win_rate=long_win_rate,
            short_win_rate=short_win_rate,
        )

    def _predict_next_bias(self, symbol: str, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        sym = [t for t in trades if t.get("symbol") == symbol]
        if len(sym) < 8:
            return {
                "symbol": symbol,
                "predicted_pnl_pct": 0.0,
                "confidence": 0.2,
                "note": "insufficient_trades",
            }

        y = np.array([float(t.get("pnl_pct", 0.0) or 0.0) for t in sym[-20:]], dtype=float)
        x = np.arange(len(y), dtype=float)

        slope, intercept = np.polyfit(x, y, 1)
        predicted = slope * (len(y)) + intercept

        # Confidence heuristic: stronger when trend is consistent and sample is larger.
        volatility = float(np.std(y)) if len(y) > 1 else 1.0
        raw_conf = min(1.0, abs(float(slope)) / (volatility + 1e-6) * 2.0)
        conf = max(0.2, min(0.9, raw_conf))

        return {
            "symbol": symbol,
            "predicted_pnl_pct": round(float(predicted), 4),
            "confidence": round(conf, 2),
            "slope": round(float(slope), 4),
            "volatility": round(volatility, 4),
        }

    def _read_current_dynamic_params(self) -> Dict[str, Any]:
        doc = self._db["agent_states"].find_one({"_id": "dynamic_parameters"}, {"_id": 0, "updated_at": 0})
        return doc or {}

    def _propose_adjustments(
        self,
        all_stats: List[SymbolStats],
        predictions: List[Dict[str, Any]],
        current_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        suggestions: Dict[str, Any] = {}

        if not all_stats:
            return {
                "summary": "no_trade_data",
                "suggestions": suggestions,
                "rationale": ["No trades in selected window"],
            }

        global_win_rate = float(np.mean([s.win_rate for s in all_stats]))
        global_pf = float(np.mean([s.profit_factor for s in all_stats]))
        global_dd = float(np.mean([s.max_drawdown_pct for s in all_stats]))

        rationale: List[str] = []

        # Risk adjustment
        if global_win_rate < 0.48 or global_pf < 1.0 or global_dd > 0.12:
            current_risk = float(current_params.get("risk_per_trade", settings.risk_per_trade))
            suggestions["risk_per_trade"] = round(
                self._clamp_param("risk_per_trade", max(0.005, current_risk * 0.85)),
                4,
            )
            rationale.append("reduce risk_per_trade due low edge or elevated drawdown")

            current_cap = float(current_params.get("max_capital_per_trade", settings.max_capital_per_trade))
            suggestions["max_capital_per_trade"] = round(
                self._clamp_param("max_capital_per_trade", max(0.08, current_cap * 0.85)),
                3,
            )
            rationale.append("reduce max_capital_per_trade to soften losses")

        # Directional quality check for LONG vs SHORT
        long_wr = np.mean([s.long_win_rate for s in all_stats if s.total_trades > 0])
        short_wr = np.mean([s.short_win_rate for s in all_stats if s.total_trades > 0])
        if long_wr + 0.07 < short_wr:
            current_long_th = float(current_params.get("rsi_long_threshold", 40.0))
            suggestions["rsi_long_threshold"] = round(
                self._clamp_param("rsi_long_threshold", min(65.0, current_long_th + 2.0)),
                2,
            )
            rationale.append("long underperforming vs short, tighten long entries")

        # Prediction-informed caution
        avg_pred = float(np.mean([p.get("predicted_pnl_pct", 0.0) for p in predictions])) if predictions else 0.0
        if avg_pred < 0:
            current_sl = float(current_params.get("stop_loss", settings.stop_loss))
            suggestions["stop_loss"] = round(
                self._clamp_param("stop_loss", max(0.01, current_sl * 0.9)),
                4,
            )
            rationale.append("negative short-term pnl forecast, tighten stop_loss")

        # Keep response concise and bounded
        bounded = {k: v for k, v in suggestions.items() if k in {
            "risk_per_trade",
            "max_capital_per_trade",
            "stop_loss",
            "take_profit",
            "rsi_long_threshold",
            "rsi_short_threshold",
            "analysis_interval_seconds",
            "leverage",
        }}

        return {
            "summary": "ok",
            "suggestions": bounded,
            "rationale": rationale or ["no parameter changes suggested"],
            "global_metrics": {
                "win_rate": round(global_win_rate, 4),
                "profit_factor": round(global_pf, 4),
                "avg_max_drawdown_pct": round(global_dd, 4),
                "long_win_rate": round(float(long_wr), 4),
                "short_win_rate": round(float(short_wr), 4),
            },
        }

    def run(self, hours: int, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        trades = self._load_trades(hours)
        symbols_to_use = symbols or sorted({t.get("symbol") for t in trades if t.get("symbol")})

        per_symbol = [self._build_symbol_stats(s, trades) for s in symbols_to_use]
        predictions = [self._predict_next_bias(s, trades) for s in symbols_to_use]
        current_params = self._read_current_dynamic_params()

        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "window_hours": hours,
            "symbols": symbols_to_use,
            "sample_size": len(trades),
            "current_dynamic_params": current_params,
            "symbol_stats": [s.__dict__ for s in per_symbol],
            "predictions": predictions,
            "snapshots_hint": {
                s: len(self._load_market_snapshots(s, limit=200)) for s in symbols_to_use
            },
            "tincho1_adjustment_brief": self._propose_adjustments(per_symbol, predictions, current_params),
        }
        return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone data insights agent for Tincho")
    parser.add_argument("--hours", type=int, default=72, help="History window in hours")
    parser.add_argument("--symbols", type=str, default="", help="CSV symbols, example: BTCUSDT,ETHUSDT")
    parser.add_argument(
        "--out",
        type=str,
        default="reports/tincho_data_insights.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    agent = TinchoDataInsightsAgent(settings.mongo_uri, settings.mongo_db_name)
    try:
        report = agent.run(hours=args.hours, symbols=symbols)
    finally:
        agent.close()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    print(f"[ok] report generated: {out_path}")
    print(f"[ok] trades analyzed: {report['sample_size']}")
    brief = report.get("tincho1_adjustment_brief", {})
    print(f"[ok] suggestions: {brief.get('suggestions', {})}")


if __name__ == "__main__":
    main()
