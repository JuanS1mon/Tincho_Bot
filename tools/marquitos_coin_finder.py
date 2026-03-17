"""
tools/marquitos_coin_finder.py
==============================
Buscador de monedas para Marquitos.

Escanea Binance Futures y devuelve las mejores candidatas para scalping:
  1. Meme coins conocidas con movimiento
  2. Altcoins con alta variación 24h (gainers / losers)
  3. Monedas con volumen relativo alto (señal de actividad inusual)

El resultado es una lista ordenada por 'score' descendiente.
La IA de Marquitos usa esta lista para elegir qué operar.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from exchange.futures_client import futures_client
from exchange.market_fetcher import market_fetcher
from tools.indicator_tool import indicator_tool
from config.logger import trading_logger as logger, error_logger

# ── Meme coins y monedas volátiles conocidas ──────────────────────────────────
MEME_COINS = {
    "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "BONKUSDT", "WIFUSDT",
    "FLOKIUSDT", "MEMEUSDT", "NEIROUSDT", "TURBOBUSD", "BABYDOGEUSDT",
    "WOJAKUSDT", "POPCATUSDT", "ACTUSDT", "TRUMPUSDT", "MOODENGUSDT",
}

# Monedas que Marquitos ignora (stablecoins, pares de bajo interés)
_BLACKLIST = {
    "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "DAIUSDT", "USTCUSDT",
    "UNIUSDT",   # a veces muy poco volumen en futuros
}

# Variación 24h mínima (%) para considerar una moneda como candidata
MIN_CHANGE_PCT = 2.0      # Mínimo +2% de variación (abs)
MIN_VOLUME_USDT = 5_000_000   # Mínimo 5M USDT de volumen 24h en futuros


class MarquitosCoinFinder:
    """
    Herramienta de descubrimiento de monedas para Marquitos.

    Uso:
        candidates = coin_finder.scan(top_n=8)
        # → [{"symbol": "PEPEUSDT", "price": ..., "change_pct": 5.2, ...}, ...]
    """

    def __init__(self) -> None:
        self._active_symbols_cache: set[str] = set()
        self._active_symbols_cache_at: float = 0.0

    def _get_active_symbols(self, max_age_seconds: int = 300) -> set[str]:
        """Retorna símbolos con estado TRADING para evitar pares cerrados/delisted."""
        now = time.time()
        if self._active_symbols_cache and (now - self._active_symbols_cache_at) < max_age_seconds:
            return self._active_symbols_cache

        try:
            info = futures_client.safe_call(futures_client.client.futures_exchange_info)
            symbols = info.get("symbols", []) if isinstance(info, dict) else []
            active = {
                str(s.get("symbol", "")).upper()
                for s in symbols
                if str(s.get("symbol", "")).upper().endswith("USDT")
                and str(s.get("status", "")).upper() == "TRADING"
            }
            if active:
                self._active_symbols_cache = active
                self._active_symbols_cache_at = now
            return active
        except Exception as exc:
            error_logger.warning("CoinFinder._get_active_symbols error: %s", exc)
            return self._active_symbols_cache

    def scan(self, top_n: int = 8) -> List[Dict[str, Any]]:
        """
        Escanea todos los pares USDT de Binance Futures y retorna los mejores
        candidatos para scalping, ordenados por score descendiente.

        Score = (|change_pct| * 0.4) + (volume_score * 0.3) + (meme_bonus * 0.3)
        """
        try:
            raw_tickers = futures_client.safe_call(
                futures_client.client.futures_ticker
            )
        except Exception as exc:
            error_logger.error("CoinFinder.scan: error obteniendo tickers: %s", exc)
            return []

        active_symbols = self._get_active_symbols()

        usdt_pairs = [
            t for t in raw_tickers
            if str(t.get("symbol", "")).endswith("USDT")
            and str(t.get("symbol", "")) not in _BLACKLIST
            and (not active_symbols or str(t.get("symbol", "")).upper() in active_symbols)
        ]

        candidates: List[Dict[str, Any]] = []

        for t in usdt_pairs:
            symbol = str(t["symbol"])
            try:
                price = float(t.get("lastPrice", 0) or 0)
                change_pct = float(t.get("priceChangePercent", 0) or 0)
                volume_usdt = float(t.get("quoteVolume", 0) or 0)

                if price <= 0 or volume_usdt < MIN_VOLUME_USDT:
                    continue
                if abs(change_pct) < MIN_CHANGE_PCT:
                    continue

                is_meme = symbol in MEME_COINS
                meme_bonus = 1.0 if is_meme else 0.0

                # Volumen score: normalizado sobre 50M USDT (ajustable)
                volume_score = min(volume_usdt / 50_000_000, 1.0)

                direction_hint = "LONG" if change_pct > 0 else "SHORT"
                score = (abs(change_pct) * 0.4) + (volume_score * 0.3) + (meme_bonus * 0.3)

                candidates.append({
                    "symbol": symbol,
                    "price": price,
                    "change_pct": round(change_pct, 2),
                    "volume_usdt": round(volume_usdt, 0),
                    "is_meme": is_meme,
                    "score": round(score, 4),
                    "direction_hint": direction_hint,
                    "category": "meme" if is_meme else "altcoin",
                })

            except Exception as exc:
                error_logger.debug("CoinFinder: error procesando %s: %s", symbol, exc)
                continue

        # Ordenar por score descendiente
        candidates.sort(key=lambda x: x["score"], reverse=True)
        result = candidates[:top_n]

        if result:
            logger.info(
                "🔍 [CoinFinder] %d candidatos encontrados | top: %s",
                len(candidates),
                ", ".join(f"{c['symbol']}({c['change_pct']:+.1f}%)" for c in result[:3]),
            )
        else:
            logger.info("🔍 [CoinFinder] Sin candidatos con los criterios actuales.")

        return result

    def enrich_with_technicals(
        self,
        candidates: List[Dict[str, Any]],
        timeframe: str = "1m",
        min_green_candles: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Enriquece cada candidato con indicadores técnicos (velas verdes, RSI, momentum).
        Descarta los que no pasan el filtro técnico de Marquitos.

        Retorna la lista filtrada (puede estar vacía si ninguno pasa).
        """
        filtered: List[Dict[str, Any]] = []

        for c in candidates:
            symbol = c["symbol"]
            try:
                df = market_fetcher.get_klines(symbol, interval=timeframe, limit=60)
                if df is None or len(df) < 15:
                    continue

                closes = df["close"].values
                opens = df["open"].values

                # ── Velas verdes consecutivas ─────────────────────────────────
                green_count = sum(
                    1 for i in range(-min_green_candles, 0)
                    if closes[i] > opens[i]
                )
                if green_count < min_green_candles:
                    continue

                # ── Momentum últimas 5 velas ──────────────────────────────────
                if closes[-6] <= 0:
                    continue
                momentum_pct = (closes[-1] - closes[-6]) / closes[-6] * 100

                # ── RSI ───────────────────────────────────────────────────────
                indicators = indicator_tool.calculate(df)
                rsi = indicators.rsi if indicators else None

                c["green_candles"] = green_count
                c["momentum_5c"] = round(momentum_pct, 3)
                c["rsi"] = round(rsi, 1) if rsi else None
                c["current_price"] = float(closes[-1])

                filtered.append(c)

            except Exception as exc:
                error_logger.debug("CoinFinder.enrich(%s): %s", symbol, exc)
                continue

        # Re-ordenar por momentum técnico (los que más suben en 1m)
        filtered.sort(key=lambda x: x.get("momentum_5c", 0), reverse=True)
        return filtered


# ── Instancia global ──────────────────────────────────────────────────────────
coin_finder = MarquitosCoinFinder()
