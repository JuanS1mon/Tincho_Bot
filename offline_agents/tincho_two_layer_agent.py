from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from openai import OpenAI

# Ensure project root is on path when running this file directly.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from offline_agents.tincho_data_insights_agent import TinchoDataInsightsAgent


def _build_layer2_prompt(layer1_report: Dict[str, Any]) -> str:
    return (
        "Eres un analista de riesgo cuantitativo para trading crypto. "
        "Recibes un reporte algoritmico de la capa 1 y debes devolver DOS recomendaciones accionables para Tincho1: una conservadora y otra agresiva. "
        "No ejecutes cambios, solo recomienda.\n\n"
        "Responde SOLO JSON valido con esta estructura exacta:\n"
        "{\n"
        "  \"status\": \"ok\" | \"caution\" | \"insufficient_data\",\n"
        "  \"confidence\": 0.0,\n"
        "  \"profiles\": {\n"
        "    \"conservative\": {\n"
        "      \"adjustments\": {\n"
        "        \"risk_per_trade\": number?,\n"
        "        \"max_capital_per_trade\": number?,\n"
        "        \"stop_loss\": number?,\n"
        "        \"take_profit\": number?,\n"
        "        \"rsi_long_threshold\": number?,\n"
        "        \"rsi_short_threshold\": number?,\n"
        "        \"analysis_interval_seconds\": number?,\n"
        "        \"leverage\": number?\n"
        "      },\n"
        "      \"expected_style\": \"capital_preservation\",\n"
        "      \"risk_note\": \"texto corto\"\n"
        "    },\n"
        "    \"aggressive\": {\n"
        "      \"adjustments\": {\n"
        "        \"risk_per_trade\": number?,\n"
        "        \"max_capital_per_trade\": number?,\n"
        "        \"stop_loss\": number?,\n"
        "        \"take_profit\": number?,\n"
        "        \"rsi_long_threshold\": number?,\n"
        "        \"rsi_short_threshold\": number?,\n"
        "        \"analysis_interval_seconds\": number?,\n"
        "        \"leverage\": number?\n"
        "      },\n"
        "      \"expected_style\": \"fast_gain\",\n"
        "      \"risk_note\": \"texto corto\"\n"
        "    }\n"
        "  },\n"
        "  \"summary\": \"texto corto\",\n"
        "  \"why\": [\"razon 1\", \"razon 2\"],\n"
        "  \"guardrails\": [\"regla 1\", \"regla 2\"]\n"
        "}\n\n"
        "Criterios:\n"
        "- Si no hay evidencia suficiente, status=insufficient_data y perfiles con adjustments vacios.\n"
        "- No inventes datos fuera del reporte.\n"
        "- Evita sobreajuste; maximo 3 ajustes simultaneos por perfil.\n"
        "- Perfil conservador: prioriza control de riesgo.\n"
        "- Perfil agresivo: puede buscar ganancia rapida, pero sin romper limites de riesgo de Tincho1.\n\n"
        "Reporte capa 1 (JSON):\n"
        f"{json.dumps(layer1_report, ensure_ascii=True)}"
    )


def _parse_json_response(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty response")

    # Handle fenced markdown responses: ```json ... ```
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()

    return json.loads(text)


def _call_llm(report: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.ai_api_key:
        return {
            "status": "insufficient_data",
            "confidence": 0.0,
            "profiles": {
                "conservative": {
                    "adjustments": {},
                    "expected_style": "capital_preservation",
                    "risk_note": "sin capa automatica por falta de API key",
                },
                "aggressive": {
                    "adjustments": {},
                    "expected_style": "fast_gain",
                    "risk_note": "sin capa automatica por falta de API key",
                },
            },
            "summary": "AI_API_KEY no configurada",
            "why": ["No se puede ejecutar la capa automatica sin API key"],
            "guardrails": ["No aplicar cambios automaticos"],
        }

    client = OpenAI(api_key=settings.ai_api_key, base_url=settings.ai_base_url)

    prompt = _build_layer2_prompt(report)
    response = client.chat.completions.create(
        model=settings.ai_model,
        temperature=0.1,
        messages=[
            {"role": "system", "content": "Responde solo JSON valido."},
            {"role": "user", "content": prompt},
        ],
    )

    raw = (response.choices[0].message.content or "").strip()
    try:
        parsed = _parse_json_response(raw)
        if "profiles" not in parsed:
            base = parsed.get("recommended_adjustments", {})
            parsed["profiles"] = {
                "conservative": {
                    "adjustments": base,
                    "expected_style": "capital_preservation",
                    "risk_note": "perfil derivado de recomendacion unica",
                },
                "aggressive": {
                    "adjustments": {},
                    "expected_style": "fast_gain",
                    "risk_note": "faltan datos del perfil agresivo en respuesta IA",
                },
            }
        return parsed
    except Exception:
        conservative = report.get("tincho1_adjustment_brief", {}).get("suggestions", {})
        return {
            "status": "caution",
            "confidence": 0.3,
            "profiles": {
                "conservative": {
                    "adjustments": conservative,
                    "expected_style": "capital_preservation",
                    "risk_note": "fallback algoritmico",
                },
                "aggressive": {
                    "adjustments": {
                        "leverage": 10,
                        "risk_per_trade": 0.01,
                    },
                    "expected_style": "fast_gain",
                    "risk_note": "fallback agresivo generico; validar manualmente",
                },
            },
            "summary": "Respuesta IA no parseable; fallback a capa algoritmica",
            "why": [raw[:400] if raw else "sin contenido"],
            "guardrails": ["Revisar manualmente antes de aplicar"],
        }


def run_two_layers(hours: int, symbols: Optional[List[str]]) -> Dict[str, Any]:
    layer1_agent = TinchoDataInsightsAgent(settings.mongo_uri, settings.mongo_db_name)
    try:
        layer1 = layer1_agent.run(hours=hours, symbols=symbols)
    finally:
        layer1_agent.close()

    layer2 = _call_llm(layer1)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "two_layers",
        "layer1_algorithmic": layer1,
        "layer2_agentic": layer2,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tincho two-layer (algorithmic + agentic) advisor")
    parser.add_argument("--hours", type=int, default=72, help="History window in hours")
    parser.add_argument("--symbols", type=str, default="", help="CSV symbols, example: BTCUSDT,ETHUSDT")
    parser.add_argument(
        "--out",
        type=str,
        default="reports/tincho_two_layer_report.json",
        help="Output JSON report path",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()] or None

    final_report = run_two_layers(hours=args.hours, symbols=symbols)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(final_report, indent=2, ensure_ascii=True), encoding="utf-8")

    layer2 = final_report.get("layer2_agentic", {})
    print(f"[ok] report generated: {out_path}")
    print(f"[ok] layer2 status: {layer2.get('status', 'unknown')}")
    cons = (layer2.get("profiles", {}) or {}).get("conservative", {}).get("adjustments", {})
    aggr = (layer2.get("profiles", {}) or {}).get("aggressive", {}).get("adjustments", {})
    print(f"[ok] layer2 conservative: {cons}")
    print(f"[ok] layer2 aggressive: {aggr}")


if __name__ == "__main__":
    main()
