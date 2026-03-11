"""
Domain Service - Market Analyzer
=================================
Analiza datos de mercado usando indicadores técnicos.
Genera un MarketSnapshot con: price, trend, momentum, volatility, volume_trend.
Estados: bullish, bearish, sideways, high_volatility.
"""

from typing import Dict, Optional

import pandas as pd

from config.logger import get_logger
from config.settings import settings
from domain.entities.market_data import MarketData, MarketSnapshot
from indicators.rsi import calculate_rsi
from indicators.macd import calculate_macd
from indicators.sma import calculate_sma
from indicators.ema import calculate_ema
from indicators.volatility import calculate_volatility, calculate_volume_trend

logger = get_logger(__name__)


class MarketAnalyzer:
    """
    Analiza el estado del mercado para cada símbolo usando indicadores técnicos.
    Genera un resumen estructurado (MarketSnapshot) que se envía a la IA.
    """

    def analyze(self, market_data: MarketData, interval: str = "1h") -> Optional[MarketSnapshot]:
        """
        Analiza un símbolo y genera un MarketSnapshot completo.
        
        Args:
            market_data: Datos de mercado del símbolo.
            interval: Intervalo a usar para el análisis principal.
            
        Returns:
            MarketSnapshot con el análisis, o None si faltan datos.
        """
        df = market_data.get_klines(interval)
        if df is None or len(df) < 50:
            logger.warning(
                f"Datos insuficientes para analizar {market_data.symbol} [{interval}]: "
                f"{len(df) if df is not None else 0} velas"
            )
            return None

        closes = df["close"].astype(float)
        volumes = df["volume"].astype(float)
        highs = df["high"].astype(float)
        lows = df["low"].astype(float)

        # --- Calcular indicadores ---
        sma_20 = calculate_sma(closes, period=20)
        sma_50 = calculate_sma(closes, period=50)
        ema_20 = calculate_ema(closes, period=20)
        rsi = calculate_rsi(closes, period=14)
        macd_line, signal_line, histogram = calculate_macd(closes)
        volatility = calculate_volatility(closes, period=30)
        vol_trend = calculate_volume_trend(volumes)

        # Valores actuales
        current_price = float(closes.iloc[-1])
        current_rsi = float(rsi.iloc[-1]) if len(rsi) > 0 else 50.0
        current_sma_20 = float(sma_20.iloc[-1]) if len(sma_20) > 0 else current_price
        current_sma_50 = float(sma_50.iloc[-1]) if len(sma_50) > 0 else current_price
        current_ema_20 = float(ema_20.iloc[-1]) if len(ema_20) > 0 else current_price
        current_volatility = float(volatility.iloc[-1]) if len(volatility) > 0 else 0.0
        current_macd = float(histogram.iloc[-1]) if len(histogram) > 0 else 0.0

        # --- Determinar tendencia ---
        trend = self._determine_trend(current_price, current_sma_20, current_sma_50, current_ema_20)

        # --- Determinar momentum ---
        momentum = self._determine_momentum(current_rsi, current_macd)

        # --- Determinar estado de volatilidad ---
        volatility_state = self._determine_volatility_state(current_volatility)

        # --- Señal MACD ---
        macd_signal = self._determine_macd_signal(macd_line, signal_line)

        # --- Estado general del mercado ---
        market_state = self._determine_market_state(
            trend, momentum, volatility_state, current_rsi
        )

        snapshot = MarketSnapshot(
            symbol=market_data.symbol,
            price=current_price,
            trend=trend,
            momentum=momentum,
            volatility=current_volatility,
            volatility_state=volatility_state,
            volume_trend=vol_trend,
            rsi=current_rsi,
            macd_signal=macd_signal,
            sma_20=current_sma_20,
            sma_50=current_sma_50,
            ema_20=current_ema_20,
            market_state=market_state,
        )

        logger.info(
            f"Análisis {market_data.symbol}: state={market_state}, "
            f"trend={trend}, RSI={current_rsi:.1f}, vol={current_volatility:.2f}%"
        )
        return snapshot

    def _determine_trend(
        self, price: float, sma_20: float, sma_50: float, ema_20: float
    ) -> str:
        """Determina la tendencia basándose en medias móviles."""
        bullish_signals = 0
        bearish_signals = 0

        # Precio vs SMA20
        if price > sma_20:
            bullish_signals += 1
        else:
            bearish_signals += 1

        # Precio vs SMA50
        if price > sma_50:
            bullish_signals += 1
        else:
            bearish_signals += 1

        # SMA20 vs SMA50 (golden/death cross)
        if sma_20 > sma_50:
            bullish_signals += 1
        else:
            bearish_signals += 1

        # EMA20 vs precio
        if price > ema_20:
            bullish_signals += 1
        else:
            bearish_signals += 1

        if bullish_signals >= 3:
            return "bullish"
        elif bearish_signals >= 3:
            return "bearish"
        return "sideways"

    def _determine_momentum(self, rsi: float, macd_histogram: float) -> str:
        """Determina el momentum basándose en RSI y MACD."""
        if rsi > 70 and macd_histogram > 0:
            return "strong_bullish"
        elif rsi > 55 and macd_histogram > 0:
            return "bullish"
        elif rsi < 30 and macd_histogram < 0:
            return "strong_bearish"
        elif rsi < 45 and macd_histogram < 0:
            return "bearish"
        return "neutral"

    def _determine_volatility_state(self, volatility: float) -> str:
        """Clasifica el nivel de volatilidad."""
        if volatility > 5.0:
            return "high"
        elif volatility > 2.5:
            return "medium"
        return "low"

    def _determine_macd_signal(
        self, macd_line: pd.Series, signal_line: pd.Series
    ) -> str:
        """Determina la señal del MACD (cruce de líneas)."""
        if len(macd_line) < 2 or len(signal_line) < 2:
            return "neutral"

        current_macd = float(macd_line.iloc[-1])
        current_signal = float(signal_line.iloc[-1])
        prev_macd = float(macd_line.iloc[-2])
        prev_signal = float(signal_line.iloc[-2])

        # Cruce alcista: MACD cruza por encima de la señal
        if prev_macd <= prev_signal and current_macd > current_signal:
            return "bullish"
        # Cruce bajista: MACD cruza por debajo de la señal
        elif prev_macd >= prev_signal and current_macd < current_signal:
            return "bearish"
        # Sin cruce pero MACD positivo
        elif current_macd > current_signal:
            return "bullish"
        elif current_macd < current_signal:
            return "bearish"
        return "neutral"

    def _determine_market_state(
        self, trend: str, momentum: str, volatility_state: str, rsi: float
    ) -> str:
        """
        Determina el estado general del mercado.
        Posibles estados: bullish, bearish, sideways, high_volatility.
        """
        # Alta volatilidad domina
        if volatility_state == "high":
            return "high_volatility"

        # Bullish fuerte
        if trend == "bullish" and momentum in ("bullish", "strong_bullish"):
            return "bullish"

        # Bearish fuerte
        if trend == "bearish" and momentum in ("bearish", "strong_bearish"):
            return "bearish"

        # RSI en extremos
        if rsi > 75:
            return "high_volatility"  # Sobrecompra = riesgo
        if rsi < 25:
            return "bearish"

        return "sideways"
