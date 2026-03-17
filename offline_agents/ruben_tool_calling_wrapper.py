"""
Ruben Tool Calling Wrapper
Offline analysis agent with LLM-driven tool calling for Tincho1 parameter optimization.

Features:
- Reads historical trading data from MongoDB
- Generates insights reports via TinchoDataInsightsAgent
- Uses two-layer analysis (algorithmic + LLM)
- Supports function calling for interactive decision-making
- Applies profile-based recommendations
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure project root is on path when running this file directly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from ai.llm_client import LLMClient, ToolCallResult
from ai.tool_definitions import RUBEN_TOOLS
from config.settings import settings
from offline_agents.tincho_data_insights_agent import TinchoDataInsightsAgent
from offline_agents import tincho_two_layer_agent as two_layer_module
from storage.state_repository import StateRepository


class RubenToolCallingWrapper:
    """
    LLM-driven wrapper for offline analysis agents.
    Supports function calling for selective analysis and profile application.
    """

    def __init__(
        self,
        mongo_uri: str = settings.mongo_uri,
        db_name: str = settings.mongo_db_name,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self._mongo_uri = mongo_uri
        self._db_name = db_name
        self._insights_agent = TinchoDataInsightsAgent(mongo_uri, db_name)
        self._llm_client = llm_client or LLMClient()
        self._state_repo = StateRepository()

        # Cache for current analysis
        self._last_analysis: Optional[Dict[str, Any]] = None
        self._last_symbols: Optional[List[str]] = None
        self._last_hours: Optional[int] = None

    def generate_insights_report(
        self, hours: int, symbols: Optional[str] = None, analysis_type: str = "simple"
    ) -> Dict[str, Any]:
        """
        Generate insights report by analyzing historical data.

        Args:
            hours: Hours to analyze (1-720)
            symbols: Comma-separated CSV symbols (e.g., "BTCUSDT,ETHUSDT")
            analysis_type: "simple" (layer 1 only) or "two_layer" (requires LLM)

        Returns:
            Dictionary with insights report
        """
        try:
            # Load trades for analysis window
            trades = self._insights_agent._load_trades(hours)
            if not trades:
                return {
                    "status": "no_data",
                    "message": f"No trades found in last {hours} hours",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            # Parse symbols
            if symbols:
                symbol_list = [s.strip() for s in symbols.split(",")]
            else:
                # Auto-detect from trades
                symbol_list = sorted(set(t.get("symbol") for t in trades if t.get("symbol")))

            # Layer 1: Algorithmic analysis
            stats = [self._insights_agent._build_symbol_stats(sym, trades) for sym in symbol_list]
            predictions = [self._insights_agent._predict_next_bias(sym, trades) for sym in symbol_list]
            current_params = self._insights_agent._read_current_dynamic_params()
            adjustments = self._insights_agent._propose_adjustments(stats, predictions, current_params)

            layer1_report = {
                "layer": 1,
                "hours": hours,
                "symbol_count": len(symbol_list),
                "total_trades": len(trades),
                "symbols": symbol_list,
                "stats": [asdict(s) for s in stats],
                "predictions": predictions,
                "current_params": current_params,
                "adjustments": adjustments,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Optional: Layer 2 (agentic analysis with LLM)
            if analysis_type == "two_layer":
                layer2_result = two_layer_module._call_llm(layer1_report)
                layer1_report["layer2"] = layer2_result

            # Cache for later use
            self._last_analysis = layer1_report
            self._last_symbols = symbol_list
            self._last_hours = hours

            return {
                "status": "success",
                "report": layer1_report,
                "message": f"Analysis complete for {len(symbol_list)} symbols, {len(trades)} trades",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def select_profile(self, profile: str, reasoning: str) -> Dict[str, Any]:
        """
        Select conservative or aggressive profile based on analysis.

        Args:
            profile: "conservative" or "aggressive"
            reasoning: Why this profile was selected

        Returns:
            Profile details and adjustments
        """
        try:
            if not self._last_analysis:
                return {
                    "status": "error",
                    "message": "No analysis available. Run generate_insights_report first.",
                }

            # Extract profile from layer 2 if available
            layer2 = self._last_analysis.get("layer2")
            if not layer2 or "profiles" not in layer2:
                return {
                    "status": "error",
                    "message": "Layer 2 analysis not available. Use analysis_type='two_layer'",
                }

            profiles = layer2.get("profiles", {})
            if profile not in profiles:
                return {
                    "status": "error",
                    "message": f"Profile '{profile}' not found. Available: {list(profiles.keys())}",
                }

            selected = profiles[profile]
            selected["selected_profile"] = profile
            selected["selection_reasoning"] = reasoning
            selected["selected_at"] = datetime.now(timezone.utc).isoformat()

            return {
                "status": "success",
                "profile": selected,
                "message": f"Selected {profile} profile",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }

    def apply_recommendations(
        self, apply_profile: str, confidence_threshold: float = 0.0
    ) -> Dict[str, Any]:
        """
        Apply selected profile recommendations to Tincho1 parameters.

        Args:
            apply_profile: "yes" to apply, "no" to skip
            confidence_threshold: Min confidence (0.0-1.0) to apply

        Returns:
            Application status and results
        """
        try:
            if apply_profile.lower() != "yes":
                return {
                    "status": "skipped",
                    "message": "Profile application declined",
                }

            if not self._last_analysis:
                return {
                    "status": "error",
                    "message": "No analysis available.",
                }

            layer2 = self._last_analysis.get("layer2")
            if not layer2:
                return {
                    "status": "error",
                    "message": "Layer 2 analysis required for application",
                }

            # Check confidence threshold
            confidence = layer2.get("confidence", 0.0)
            if confidence < confidence_threshold:
                return {
                    "status": "skipped",
                    "message": f"Confidence {confidence} below threshold {confidence_threshold}",
                    "confidence": confidence,
                }

            # Apply adjustments (Layer 1 suggestions first, then Layer 2 profile)
            adjustments = {
                "source": "ruben_offline_analysis",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "layer1_adjustments": self._last_analysis.get("adjustments", {}).get("suggestions", {}),
                "layer2_profile": layer2.get("profiles", {}).get("conservative", {}),
                "confidence": confidence,
            }

            # Store in state repository (non-destructive, advisory only)
            self._state_repo.update_dynamic_parameters(adjustments)

            return {
                "status": "applied",
                "adjustments": adjustments,
                "message": "Profile recommendations applied to dynamic parameters",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": str(e),
            }

    def skip_analysis(self, reason: str) -> Dict[str, Any]:
        """
        Skip analysis if insufficient data or user discretion.

        Args:
            reason: Why analysis is skipped

        Returns:
            Skip confirmation
        """
        return {
            "status": "skipped",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Analysis skipped by user request",
        }

    def run_with_tool_calling(self, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Run Ruben with LLM-driven tool calling.
        LLM decides which tools to call and in what order.

        Args:
            system_prompt: Optional custom system prompt

        Returns:
            Tool calling result and final analysis
        """
        if not system_prompt:
            system_prompt = (
                "Eres Ruben, el agente offline de análisis para Tincho1. "
                "Tu rol es analizar datos históricos de trading y recomendar ajustes de parámetros. "
                "Tienes acceso a 4 herramientas:\n"
                "1. generate_insights_report: Analiza datos históricos (especifica horas, símbolos, tipo)\n"
                "2. select_profile: Elige entre perfil conservador (preservación capital) o agresivo (ganancias rápidas)\n"
                "3. apply_recommendations: Aplica las recomendaciones a Tincho1\n"
                "4. skip_analysis: Salta si datos insuficientes\n\n"
                "Flujo típico: generar reporte → analizar → seleccionar perfil → aplicar recomendaciones.\n"
                "Si los datos son insuficientes, usa skip_analysis con una razón clara."
            )

        user_prompt = (
            "Analiza el último día de trading (24 horas) e implementa recomendaciones "
            "si tienes confianza en el análisis. "
            "Símbolo: BTCUSDT, ETHUSDT"
        )

        # Call LLM with tool calling
        result = self._llm_client.decide_with_tools(
            prompt=f"{system_prompt}\n\nUser Request: {user_prompt}",
            tools=RUBEN_TOOLS,
        )

        if not result:
            return {
                "status": "error",
                "message": "LLM tool calling failed",
            }

        # Execute tool calls sequentially
        tool_results: List[Dict[str, Any]] = []
        current_tool = result.tool_name
        current_params = result.tool_params or {}

        while current_tool:
            # Execute current tool
            if current_tool == "generate_insights_report":
                tool_result = self.generate_insights_report(
                    hours=current_params.get("hours", 24),
                    symbols=current_params.get("symbols"),
                    analysis_type=current_params.get("analysis_type", "simple"),
                )
            elif current_tool == "select_profile":
                tool_result = self.select_profile(
                    profile=current_params.get("profile", "conservative"),
                    reasoning=current_params.get("reasoning", ""),
                )
            elif current_tool == "apply_recommendations":
                tool_result = self.apply_recommendations(
                    apply_profile=current_params.get("apply_profile", "no"),
                    confidence_threshold=current_params.get("confidence_threshold", 0.0),
                )
            elif current_tool == "skip_analysis":
                tool_result = self.skip_analysis(
                    reason=current_params.get("reason", "insufficient data"),
                )
            else:
                tool_result = {
                    "status": "error",
                    "message": f"Unknown tool: {current_tool}",
                }

            tool_results.append({
                "tool": current_tool,
                "params": current_params,
                "result": tool_result,
            })

            # TODO: In a real implementation, you'd feed tool results back to LLM
            # for subsequent tool calls. For now, we stop after first tool.
            break

        return {
            "status": "success",
            "tool_calls": tool_results,
            "message": "Ruben analysis complete",
        }


async def run_ruben_analysis() -> Dict[str, Any]:
    """
    Scheduled task to run Ruben analysis periodically.
    Can be called from agent_runner.py or a scheduler.
    """
    if not settings.tool_calling_ruben:
        return {
            "status": "disabled",
            "message": "Ruben tool calling disabled",
        }

    wrapper = RubenToolCallingWrapper()
    result = wrapper.run_with_tool_calling()
    return result


if __name__ == "__main__":
    import asyncio

    result = asyncio.run(run_ruben_analysis())
    print(json.dumps(result, indent=2, default=str))
