"""
analysis/volume_analyzer.py
============================
Analiza la tendencia del volumen comparando el volumen actual
con el promedio móvil de 20 períodos.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class VolumeAnalysis:
    current_volume: float
    avg_volume: float
    volume_ratio: float        # current / avg
    trend: str                 # INCREASING | DECREASING | NORMAL
    is_high_volume: bool       # ratio > 1.5


class VolumeAnalyzer:
    """Evalúa la tendencia y magnitud del volumen."""

    HIGH_VOLUME_THRESHOLD: float = 1.5   # 150% del promedio
    LOW_VOLUME_THRESHOLD: float = 0.7    # 70% del promedio

    def analyze(self, df: pd.DataFrame) -> VolumeAnalysis:
        """
        Recibe DataFrame OHLCV y retorna análisis de volumen.
        Usa los últimos 3 períodos para determinar tendencia.
        """
        if len(df) < 20:
            return VolumeAnalysis(0, 0, 1.0, "NORMAL", False)

        volume = df["volume"]
        current = float(volume.iloc[-1])
        avg = float(volume.rolling(20).mean().iloc[-1])
        ratio = current / avg if avg > 0 else 1.0

        # Tendencia: compara últimas 3 velas
        last_3 = volume.iloc[-3:].values
        if last_3[-1] > last_3[-2] > last_3[-3]:
            trend = "INCREASING"
        elif last_3[-1] < last_3[-2] < last_3[-3]:
            trend = "DECREASING"
        else:
            trend = "NORMAL"

        return VolumeAnalysis(
            current_volume=round(current, 2),
            avg_volume=round(avg, 2),
            volume_ratio=round(ratio, 3),
            trend=trend,
            is_high_volume=ratio >= self.HIGH_VOLUME_THRESHOLD,
        )


# Instancia global
volume_analyzer = VolumeAnalyzer()
