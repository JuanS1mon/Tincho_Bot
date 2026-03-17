"""
ai/tool_definitions.py
======================
Definiciones de tools (function calling) para los agentes.

Se mantienen separadas del cliente LLM para reutilizar los schemas
en Tincho1, Tincho2 y Marquitos.
"""
from __future__ import annotations

from typing import Any, Dict, List


def _num_field(description: str, minimum: float, maximum: float) -> Dict[str, Any]:
    return {
        "type": "number",
        "description": description,
        "minimum": minimum,
        "maximum": maximum,
    }


TINCHO1_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "open_position",
            "description": "Abrir una posicion de trading si las reglas del sistema lo permiten.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Simbolo, por ejemplo BTCUSDT"},
                    "direction": {
                        "type": "string",
                        "description": "Direccion del trade",
                        "enum": ["LONG", "SHORT"],
                    },
                    "capital_usage": _num_field(
                        "Fraccion de capital a usar. Rango 0.0 a 0.50", 0.0, 0.50
                    ),
                    "reasoning": {"type": "string", "description": "Razon resumida de la decision"},
                },
                "required": ["symbol", "direction", "capital_usage"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip_trade",
            "description": "No abrir trade en este ciclo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Motivo para omitir el trade"},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "adjust_parameters",
            "description": "Ajustar parametros dinamicos del agente sin ejecutar trade directo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leverage": _num_field("Apalancamiento sugerido", 1, 25),
                    "max_capital_per_trade": _num_field("Capital maximo por trade", 0.05, 0.70),
                    "risk_per_trade": _num_field("Riesgo por trade", 0.005, 0.05),
                    "stop_loss": _num_field("Stop loss porcentual", 0.01, 0.08),
                    "take_profit": _num_field("Take profit porcentual", 0.0, 0.30),
                    "profit_lock_retrace_pct": _num_field("Retroceso para lock de ganancia", 0.05, 0.50),
                    "analysis_interval_seconds": _num_field("Intervalo entre ciclos en segundos", 10, 300),
                    "timeframe": {
                        "type": "string",
                        "description": "Timeframe para analisis",
                        "enum": ["1m", "5m", "15m", "1h", "4h"],
                    },
                    "reasoning": {"type": "string", "description": "Razon del ajuste"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "close_position",
            "description": "Cerrar una posicion abierta por gestion de riesgo o cambio de mercado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Simbolo a cerrar"},
                    "reason": {"type": "string", "description": "Motivo del cierre"},
                },
                "required": ["symbol", "reason"],
                "additionalProperties": False,
            },
        },
    },
]


TINCHO2_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "apply_parameters",
            "description": "Aplicar cambios a parametros dinamicos del bot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "leverage": _num_field("Apalancamiento sugerido", 1, 25),
                    "max_capital_per_trade": _num_field("Capital maximo por trade", 0.05, 0.70),
                    "risk_per_trade": _num_field("Riesgo por trade", 0.005, 0.05),
                    "stop_loss": _num_field("Stop loss porcentual", 0.01, 0.08),
                    "take_profit": _num_field("Take profit porcentual", 0.0, 0.30),
                    "analysis_interval_seconds": _num_field("Intervalo entre ciclos en segundos", 10, 300),
                    "timeframe": {
                        "type": "string",
                        "description": "Timeframe para analisis",
                        "enum": ["1m", "5m", "15m", "1h", "4h"],
                    },
                    "reasoning": {"type": "string", "description": "Razon del ajuste"},
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_snapshot",
            "description": "Consultar snapshot de mercado de un simbolo monitoreado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Simbolo a consultar"},
                },
                "required": ["symbol"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_manual_position",
            "description": "Abrir posicion manual en un simbolo usando un porcentaje del capital disponible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Simbolo a operar"},
                    "pct_capital": _num_field("Porcentaje de capital disponible", 0.01, 0.50),
                },
                "required": ["symbol", "pct_capital"],
                "additionalProperties": False,
            },
        },
    },
]


MARQUITOS_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "execute_scalp",
            "description": "Ejecutar un scalp rapido sobre el simbolo elegido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Simbolo a operar"},
                    "direction": {
                        "type": "string",
                        "description": "Direccion del scalp",
                        "enum": ["LONG", "SHORT"],
                    },
                    "reasoning": {"type": "string", "description": "Razon de la eleccion"},
                },
                "required": ["symbol", "direction"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip_all",
            "description": "No operar en este scan de Marquitos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Motivo para no operar"},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]


RUBEN_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "generate_insights_report",
            "description": "Generar reporte analítico offline basado en datos históricos de MongoDB.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hours": _num_field("Horas de datos históricos a analizar", 1, 720),
                    "symbols": {
                        "type": "string",
                        "description": "Símbolos CSV (ej: BTCUSDT,ETHUSDT)",
                    },
                    "analysis_type": {
                        "type": "string",
                        "description": "Tipo de análisis",
                        "enum": ["simple", "two_layer"],
                    },
                },
                "required": ["hours"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "select_profile",
            "description": "Seleccionar perfil de recomendación (conservador o agresivo).",
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "string",
                        "description": "Perfil a seleccionar",
                        "enum": ["conservative", "aggressive"],
                    },
                    "reasoning": {"type": "string", "description": "Motivo de la selección"},
                },
                "required": ["profile"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_recommendations",
            "description": "Aplicar recomendaciones de Ruben a Tincho1.",
            "parameters": {
                "type": "object",
                "properties": {
                    "apply_profile": {"type": "string", "description": "Aplicar profil seleccionado", "enum": ["yes", "no"]},
                    "confidence_threshold": _num_field("Confianza mínima para aplicar", 0.0, 1.0),
                },
                "required": ["apply_profile"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skip_analysis",
            "description": "Omitir análisis Ruben si no hay datos suficientes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Motivo para omitir análisis"},
                },
                "required": ["reason"],
                "additionalProperties": False,
            },
        },
    },
]
