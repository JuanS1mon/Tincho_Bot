"""
Advanced - Manipulation Detector
===================================
Detecta patrones de manipulación de mercado:
  - Spoofing: órdenes grandes que aparecen y desaparecen.
  - Wash Trading: volumen anormal sin movimiento de precio.
  - Pump & Dump: spike de precio + volumen con reversión rápida.
Umbrales configurables desde .env.
Si se detecta manipulación → RiskManager reduce exposición o cancela.
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional

from config.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)


class ManipulationDetector:
    """
    Detecta patrones de manipulación de mercado usando REST polling.
    Cada patrón tiene umbrales configurables desde .env.
    """

    def __init__(self):
        self.volume_spike_threshold = settings.MANIPULATION_VOLUME_SPIKE
        self.price_reversal_threshold = settings.MANIPULATION_PRICE_REVERSAL
        # Historial para comparar entre ciclos
        self._prev_order_books: Dict[str, dict] = {}

    def detect(
        self,
        symbol: str,
        klines_df: pd.DataFrame,
        order_book: dict,
        recent_trades: List[dict],
    ) -> Dict:
        """
        Ejecuta todas las detecciones de manipulación para un símbolo.
        
        Args:
            symbol: Par de trading.
            klines_df: DataFrame de velas recientes.
            order_book: Order book actual.
            recent_trades: Trades recientes.
            
        Returns:
            Dict con flags de manipulación y detalles.
        """
        results = {
            "symbol": symbol,
            "timestamp": datetime.utcnow().isoformat(),
            "spoofing": False,
            "wash_trading": False,
            "pump_dump": False,
            "manipulation_detected": False,
            "details": [],
        }

        # --- 1. Detección de Spoofing ---
        spoofing = self._detect_spoofing(symbol, order_book)
        if spoofing:
            results["spoofing"] = True
            results["details"].append(spoofing)

        # --- 2. Detección de Wash Trading ---
        wash = self._detect_wash_trading(symbol, klines_df)
        if wash:
            results["wash_trading"] = True
            results["details"].append(wash)

        # --- 3. Detección de Pump & Dump ---
        pump_dump = self._detect_pump_dump(symbol, klines_df)
        if pump_dump:
            results["pump_dump"] = True
            results["details"].append(pump_dump)

        # Flag general
        results["manipulation_detected"] = (
            results["spoofing"] or results["wash_trading"] or results["pump_dump"]
        )

        if results["manipulation_detected"]:
            logger.warning(
                f"⚠️ MANIPULACIÓN detectada en {symbol}: "
                f"spoofing={results['spoofing']}, "
                f"wash={results['wash_trading']}, "
                f"pump_dump={results['pump_dump']}"
            )
        else:
            logger.debug(f"✅ Sin manipulación detectada en {symbol}")

        # Guardar order book actual para comparar en el próximo ciclo
        self._prev_order_books[symbol] = order_book

        return results

    def _detect_spoofing(self, symbol: str, current_ob: dict) -> Optional[dict]:
        """
        Detecta spoofing comparando el order book actual con el anterior.
        Spoofing: órdenes grandes que desaparecen entre ciclos (> 80% removidas).
        """
        prev_ob = self._prev_order_books.get(symbol)
        if not prev_ob:
            return None  # Primera ejecución, sin referencia

        prev_bids = {price: qty for price, qty in prev_ob.get("bids", [])[:20]}
        curr_bids = {price: qty for price, qty in current_ob.get("bids", [])[:20]}

        prev_asks = {price: qty for price, qty in prev_ob.get("asks", [])[:20]}
        curr_asks = {price: qty for price, qty in current_ob.get("asks", [])[:20]}

        # Contar órdenes grandes que desaparecieron
        vanished_bids = 0
        total_large_bids = 0
        for price, qty in prev_bids.items():
            if qty > 0:
                # Considerar "grande" si está por encima de la media * 2
                all_prev_qty = list(prev_bids.values())
                mean_qty = np.mean(all_prev_qty) if all_prev_qty else 0
                if qty > mean_qty * 2:
                    total_large_bids += 1
                    if price not in curr_bids or curr_bids[price] < qty * 0.2:
                        vanished_bids += 1

        vanished_asks = 0
        total_large_asks = 0
        for price, qty in prev_asks.items():
            if qty > 0:
                all_prev_qty = list(prev_asks.values())
                mean_qty = np.mean(all_prev_qty) if all_prev_qty else 0
                if qty > mean_qty * 2:
                    total_large_asks += 1
                    if price not in curr_asks or curr_asks[price] < qty * 0.2:
                        vanished_asks += 1

        total_large = total_large_bids + total_large_asks
        total_vanished = vanished_bids + vanished_asks

        if total_large >= 3 and total_vanished / max(total_large, 1) > 0.6:
            return {
                "type": "spoofing",
                "description": (
                    f"{total_vanished}/{total_large} órdenes grandes desaparecieron "
                    f"entre ciclos"
                ),
                "severity": "high" if total_vanished > 5 else "medium",
            }

        return None

    def _detect_wash_trading(
        self, symbol: str, df: pd.DataFrame
    ) -> Optional[dict]:
        """
        Detecta wash trading: volumen anormalmente alto sin movimiento de precio.
        Señal: volumen > N veces el promedio Y cambio de precio < 0.5%.
        """
        if df is None or len(df) < 20:
            return None

        volumes = df["volume"].astype(float)
        closes = df["close"].astype(float)

        # Últimas 5 velas vs promedio histórico
        recent_volume = volumes.tail(5).mean()
        avg_volume = volumes.mean()
        recent_price_change = abs(
            (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5]
        )

        volume_ratio = recent_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio > self.volume_spike_threshold and recent_price_change < 0.005:
            return {
                "type": "wash_trading",
                "description": (
                    f"Volumen {volume_ratio:.1f}x el promedio "
                    f"con cambio de precio de solo {recent_price_change:.3%}"
                ),
                "volume_ratio": round(volume_ratio, 2),
                "price_change": round(recent_price_change, 4),
                "severity": "medium",
            }

        return None

    def _detect_pump_dump(
        self, symbol: str, df: pd.DataFrame
    ) -> Optional[dict]:
        """
        Detecta pump & dump: spike rápido de precio seguido de reversión.
        Señal: subida > threshold% seguida de caída > threshold% en pocas velas.
        """
        if df is None or len(df) < 10:
            return None

        closes = df["close"].astype(float).tail(10)
        threshold = self.price_reversal_threshold

        # Buscar patrón: subida seguida de caída
        for i in range(1, len(closes) - 1):
            if i < 1:
                continue

            prev_price = closes.iloc[i - 1]
            peak_price = closes.iloc[i]
            current_price = closes.iloc[-1]

            rise = (peak_price - prev_price) / prev_price if prev_price > 0 else 0
            fall = (peak_price - current_price) / peak_price if peak_price > 0 else 0

            if rise > threshold and fall > threshold:
                return {
                    "type": "pump_dump",
                    "description": (
                        f"Subida de {rise:.2%} seguida de caída de {fall:.2%}"
                    ),
                    "rise": round(rise, 4),
                    "fall": round(fall, 4),
                    "severity": "high",
                }

        return None
