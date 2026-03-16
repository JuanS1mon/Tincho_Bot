"""
config/agent_config.py
=======================
Lee y parsea agente.md — la fuente de verdad para el comportamiento del agente.

Expone:
  - agent_config.system_prompt   → string con el system prompt para la IA
  - agent_config.param_bounds    → dict {nombre: (min, max, cast)} para ParametersManager
  - agent_config.valid_timeframes→ set de timeframes permitidos
  - agent_config.default_timeframe → string
  - agent_config.reload()         → recarga el archivo sin reiniciar el proceso

El archivo agente.md usa secciones marcadas con "## 🧠 Prompt del Sistema",
"## 📐 Límites de Parámetros", etc. para separar la información.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Set, Tuple

from config.logger import trading_logger as logger, error_logger

# Ubicación del archivo de configuración del agente
AGENTE_MD_PATH = Path(__file__).parent.parent / "tincho1.md"


class AgentConfig:
    """
    Parsea agente.md y expone su contenido como atributos tipados.
    Se puede recargar en caliente con .reload().
    """

    def __init__(self) -> None:
        self.system_prompt: str = ""
        self.param_bounds: Dict[str, Tuple] = {}
        self.valid_timeframes: Set[str] = set()
        self.default_timeframe: str = "15m"
        self._raw: str = ""
        self.load()

    # ── Carga principal ───────────────────────────────────────────────────────

    def load(self) -> None:
        """Lee tincho1.md y parsea todas las secciones."""
        if not AGENTE_MD_PATH.exists():
            error_logger.error(
                "tincho1.md no encontrado en %s — usando defaults hardcodeados", AGENTE_MD_PATH
            )
            self._apply_defaults()
            return

        self._raw = AGENTE_MD_PATH.read_text(encoding="utf-8")
        self.system_prompt = self._parse_system_prompt()
        self.param_bounds = self._parse_param_bounds()
        self.valid_timeframes, self.default_timeframe = self._parse_timeframes()

        logger.info(
            "tincho1.md cargado | %d parámetros | timeframes=%s | prompt=%d chars",
            len(self.param_bounds),
            sorted(self.valid_timeframes),
            len(self.system_prompt),
        )

    def reload(self) -> None:
        """Recarga el archivo sin reiniciar el proceso (hot-reload)."""
        logger.info("Recargando tincho1.md...")
        self.load()

    # ── Parsers ───────────────────────────────────────────────────────────────

    def _parse_system_prompt(self) -> str:
        """
        Extrae el contenido de la sección '## 🧠 Prompt del Sistema'.
        Todo lo que hay entre esa cabecera y el siguiente '---' o '## ' es el system prompt.
        """
        # Buscar la sección por cabecera (emoji opcional)
        pattern = r"##\s+(?:🧠\s+)?Prompt del Sistema\s*\n(.*?)(?=\n---|\n##\s|\Z)"
        match = re.search(pattern, self._raw, re.DOTALL | re.IGNORECASE)
        if not match:
            error_logger.warning("agente.md: no se encontró '## Prompt del Sistema' — usando default")
            return self._default_system_prompt()

        content = match.group(1).strip()
        if not content:
            return self._default_system_prompt()

        return content

    def _parse_param_bounds(self) -> Dict[str, Tuple]:
        """
        Parsea la tabla markdown de límites:
          | parametro | min | max | tipo | default |
        Retorna dict {nombre: (min, max, cast_fn)} compatible con ParametersManager.
        """
        bounds: Dict[str, Tuple] = {}

        # Encontrar la sección de límites
        section_pattern = r"##\s+(?:📐\s+)?L[ií]mites de Par[aá]metros\s*\n(.*?)(?=\n##\s|\Z)"
        section_match = re.search(section_pattern, self._raw, re.DOTALL | re.IGNORECASE)
        if not section_match:
            error_logger.warning("agente.md: no se encontró sección de límites — usando defaults")
            return self._default_param_bounds()

        section = section_match.group(1)

        # Parsear cada fila de la tabla (ignorar cabecera y separador)
        row_pattern = r"^\|\s*([a-z0-9_]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*(int|float)\s*\|.*\|"
        for line in section.splitlines():
            m = re.match(row_pattern, line.strip(), re.IGNORECASE)
            if not m:
                continue
            name = m.group(1).strip()
            try:
                cast = int if m.group(4).lower() == "int" else float
                min_val = cast(m.group(2))
                max_val = cast(m.group(3))
                bounds[name] = (min_val, max_val, cast)
            except (ValueError, TypeError) as exc:
                error_logger.warning("agente.md: fila inválida para '%s': %s", name, exc)

        if not bounds:
            error_logger.warning("agente.md: tabla de parámetros vacía — usando defaults")
            return self._default_param_bounds()

        return bounds

    def _parse_timeframes(self) -> Tuple[Set[str], str]:
        """
        Parsea la sección '## ⏱️ Timeframes Válidos'.
        Extrae el conjunto de timeframes y el default.
        """
        # Encontrar sección
        section_pattern = r"##\s+(?:⏱️\s+)?Timeframes V[aá]lidos\s*\n(.*?)(?=\n##\s|\Z)"
        section_match = re.search(section_pattern, self._raw, re.DOTALL | re.IGNORECASE)

        valid: Set[str] = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h"}  # fallback
        default = "15m"

        if not section_match:
            return valid, default

        section = section_match.group(1)

        # Primera línea no vacía con comas → lista de timeframes
        for line in section.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Buscar tokens que parezcan timeframes: dígito + unidad
            tokens = re.findall(r"\d+[mhd]", line, re.IGNORECASE)
            if tokens:
                valid = {t.lower() for t in tokens}
                break

        # Buscar "Timeframe por defecto: XY"
        default_match = re.search(r"[Tt]imeframe por defecto[:\s]+(\d+[mhd])", section)
        if default_match:
            default = default_match.group(1).lower()

        return valid, default

    # ── Defaults (si agente.md no existe o tiene errores) ────────────────────

    def _apply_defaults(self) -> None:
        self.system_prompt = self._default_system_prompt()
        self.param_bounds = self._default_param_bounds()
        self.valid_timeframes = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h"}
        self.default_timeframe = "15m"

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "You are a professional quantitative crypto trader specialized in futures markets. "
            "Analyze market data and decide if a futures trade should be opened. "
            "Be conservative — only approve trades with strong confluence of signals. "
            "Only suggest parameter_adjustments when there is clear evidence they are needed. "
            "Always respond ONLY with valid JSON. No explanations, no markdown, just raw JSON."
        )

    @staticmethod
    def _default_param_bounds() -> Dict[str, Tuple]:
        return {
            "leverage":                  (1,     20,   int),
            "max_capital_per_trade":     (0.05,  0.50, float),
            "risk_per_trade":            (0.005, 0.03, float),
            "stop_loss":                 (0.01,  0.05, float),
            "take_profit":               (0.02,  0.15, float),
            "analysis_interval_seconds": (180,   3600, int),
            "sma20_proximity_pct":       (0.005, 0.05, float),
            "rsi_long_threshold":        (40.0,  65.0, float),
            "rsi_short_threshold":       (30.0,  55.0, float),
            "liquidation_dominance_ratio": (1.2, 3.0, float),
        }

    # ── Consultas de ayuda ────────────────────────────────────────────────────

    def bounds_summary(self) -> str:
        """Resumen legible de los límites parseados de agente.md."""
        lines = [f"  • {k}: [{v[0]}, {v[1]}] ({v[2].__name__})" for k, v in self.param_bounds.items()]
        return "\n".join(lines)


# Singleton global — se carga una vez al importar
agent_config = AgentConfig()
