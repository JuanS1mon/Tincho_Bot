"""
Indicador Técnico - Volatility
================================
Calcula la volatilidad rolling (desviación estándar anualizada)
y la tendencia de volumen (increasing, decreasing, stable).
"""

import numpy as np
import pandas as pd


def calculate_volatility(closes: pd.Series, period: int = 30) -> pd.Series:
    """
    Calcula la volatilidad como desviación estándar porcentual de retornos.
    
    Args:
        closes: Serie de precios de cierre.
        period: Periodo de la ventana rolling (default 30).
        
    Returns:
        Serie con la volatilidad porcentual rolling.
    """
    # Retornos logarítmicos
    log_returns = np.log(closes / closes.shift(1))

    # Volatilidad rolling (desviación estándar * 100 para porcentaje)
    volatility = log_returns.rolling(window=period).std() * 100

    return volatility


def calculate_volume_trend(
    volumes: pd.Series, short_period: int = 7, long_period: int = 21
) -> str:
    """
    Determina la tendencia del volumen comparando promedios corto y largo plazo.
    
    Args:
        volumes: Serie de volúmenes.
        short_period: Periodo corto para media de volumen (default 7).
        long_period: Periodo largo para media de volumen (default 21).
        
    Returns:
        "increasing", "decreasing" o "stable".
    """
    if len(volumes) < long_period:
        return "stable"

    avg_short = volumes.tail(short_period).mean()
    avg_long = volumes.tail(long_period).mean()

    if avg_long == 0:
        return "stable"

    ratio = avg_short / avg_long

    if ratio > 1.15:
        return "increasing"
    elif ratio < 0.85:
        return "decreasing"
    return "stable"


def calculate_atr(
    highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14
) -> pd.Series:
    """
    Calcula el Average True Range (ATR).
    Útil para medir la volatilidad intradía.
    
    Args:
        highs: Serie de precios máximos.
        lows: Serie de precios mínimos.
        closes: Serie de precios de cierre.
        period: Periodo del ATR (default 14).
        
    Returns:
        Serie con los valores del ATR.
    """
    prev_close = closes.shift(1)

    # True Range: máximo de los 3 rangos posibles
    tr1 = highs - lows
    tr2 = (highs - prev_close).abs()
    tr3 = (lows - prev_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR es la EMA del True Range
    atr = true_range.ewm(span=period, adjust=False).mean()

    return atr
