"""
Indicador Técnico - SMA (Simple Moving Average)
=================================================
Calcula la media móvil simple con periodo configurable.
Periodos estándar: SMA20 y SMA50.
"""

import pandas as pd


def calculate_sma(closes: pd.Series, period: int = 20) -> pd.Series:
    """
    Calcula la Simple Moving Average (SMA).
    
    Args:
        closes: Serie de precios de cierre.
        period: Periodo de la media móvil (default 20).
        
    Returns:
        Serie con los valores de la SMA.
    """
    return closes.rolling(window=period).mean()


def calculate_sma_crossover(closes: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    """
    Detecta cruces entre SMA rápida y SMA lenta.
    
    Returns:
        Serie con valores:
            1  = Golden Cross (SMA rápida cruza por encima de lenta)
           -1  = Death Cross (SMA rápida cruza por debajo de lenta)
            0  = Sin cruce
    """
    sma_fast = calculate_sma(closes, fast)
    sma_slow = calculate_sma(closes, slow)

    # Posición relativa actual y anterior
    position = (sma_fast > sma_slow).astype(int)
    crossover = position.diff()

    return crossover.fillna(0).astype(int)
