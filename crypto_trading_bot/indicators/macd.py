"""
Indicador Técnico - MACD (Moving Average Convergence Divergence)
=================================================================
Calcula MACD line, Signal line e Histograma.
Parámetros estándar: fast=12, slow=26, signal=9.
"""

import pandas as pd
from typing import Tuple


def calculate_macd(
    closes: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calcula el MACD (Moving Average Convergence Divergence).
    
    Args:
        closes: Serie de precios de cierre.
        fast_period: Periodo de la EMA rápida (default 12).
        slow_period: Periodo de la EMA lenta (default 26).
        signal_period: Periodo de la línea de señal (default 9).
        
    Returns:
        Tuple de 3 Series:
            - macd_line: Línea MACD (EMA_fast - EMA_slow)
            - signal_line: Línea de señal (EMA del MACD)
            - histogram: Histograma (MACD - Signal)
    """
    # EMAs
    ema_fast = closes.ewm(span=fast_period, adjust=False).mean()
    ema_slow = closes.ewm(span=slow_period, adjust=False).mean()

    # Línea MACD
    macd_line = ema_fast - ema_slow

    # Línea de señal
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()

    # Histograma
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram
