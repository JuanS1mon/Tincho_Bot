"""
Indicador Técnico - EMA (Exponential Moving Average)
=====================================================
Calcula la media móvil exponencial con periodo configurable.
Periodo estándar: EMA20.
"""

import pandas as pd


def calculate_ema(closes: pd.Series, period: int = 20) -> pd.Series:
    """
    Calcula la Exponential Moving Average (EMA).
    
    La EMA da más peso a los datos recientes, reaccionando más
    rápido a cambios de precio que la SMA.
    
    Args:
        closes: Serie de precios de cierre.
        period: Periodo de la EMA (default 20).
        
    Returns:
        Serie con los valores de la EMA.
    """
    return closes.ewm(span=period, adjust=False).mean()
