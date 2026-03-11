"""
Indicador Técnico - RSI (Relative Strength Index)
===================================================
Calcula el RSI con periodo configurable (default 14).
RSI > 70 = sobrecompra, RSI < 30 = sobreventa.
"""

import pandas as pd


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcula el Relative Strength Index (RSI).
    
    Args:
        closes: Serie de precios de cierre.
        period: Periodo del RSI (default 14).
        
    Returns:
        Serie con los valores del RSI (0-100).
    """
    delta = closes.diff()

    # Separar ganancias y pérdidas
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    # Media móvil exponencial de ganancias y pérdidas
    avg_gains = gains.ewm(com=period - 1, min_periods=period).mean()
    avg_losses = losses.ewm(com=period - 1, min_periods=period).mean()

    # Relative Strength
    rs = avg_gains / avg_losses.replace(0, float('inf'))

    # RSI
    rsi = 100 - (100 / (1 + rs))

    return rsi
