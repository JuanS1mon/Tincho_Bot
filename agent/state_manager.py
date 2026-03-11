"""
agent/state_manager.py
=======================
Dataclasses que representan el estado interno del agente.
Publicados a la API HTTP para visualización externa.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class MarketSnapshot:
    """Estado del mercado para un símbolo en un momento dado."""
    symbol: str
    price: float
    trend: str
    rsi: float
    sma20: float
    sma50: float
    volume_trend: str
    oi_trend: str
    oi_signal: str
    funding_rate: float
    orderbook_imbalance: str
    liquidation_signal: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SignalState:
    """Señal detectada para un símbolo."""
    symbol: str
    signal: str          # LONG | SHORT | NO_SIGNAL
    strategy: str        # PULLBACK | BREAKOUT | NONE
    confidence: float
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SimulationState:
    """Resultado de la simulación previa al trade."""
    direction: str
    winrate: float
    expected_profit_pct: float
    max_drawdown_pct: float
    recommendation: str  # PROCEED | SKIP
    skip_reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AIDecisionState:
    """Decisión tomada por la IA."""
    trade: bool
    symbol: str
    direction: str
    capital_usage: float
    confidence: float
    reasoning: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentState:
    """Estado global del agente — expuesto por la API HTTP."""
    status: str = "IDLE"        # IDLE | ANALYZING | TRADING | ERROR | STOPPED
    cycle: int = 0
    last_cycle_time: float = 0.0
    last_error: str = ""

    # Snapshots por símbolo
    market_snapshots: Dict[str, MarketSnapshot] = field(default_factory=dict)
    signals: Dict[str, SignalState] = field(default_factory=dict)
    last_simulation: Optional[SimulationState] = None
    last_ai_decision: Optional[AIDecisionState] = None

    # Historial de logs del ciclo actual (últimas N entradas)
    cycle_logs: List[str] = field(default_factory=list)

    def update_market(self, snapshot: MarketSnapshot) -> None:
        self.market_snapshots[snapshot.symbol] = snapshot

    def update_signal(self, signal: SignalState) -> None:
        self.signals[signal.symbol] = signal

    def add_log(self, msg: str, max_logs: int = 100) -> None:
        self.cycle_logs.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(self.cycle_logs) > max_logs:
            self.cycle_logs = self.cycle_logs[-max_logs:]

    def to_dict(self) -> Dict[str, Any]:
        """Serializa el estado a dict para la API HTTP."""
        return {
            "status": self.status,
            "cycle": self.cycle,
            "last_cycle_time": self.last_cycle_time,
            "last_error": self.last_error,
            "market_snapshots": {
                sym: asdict(snap)
                for sym, snap in self.market_snapshots.items()
            },
            "signals": {
                sym: asdict(sig)
                for sym, sig in self.signals.items()
            },
            "last_simulation": asdict(self.last_simulation) if self.last_simulation else None,
            "last_ai_decision": asdict(self.last_ai_decision) if self.last_ai_decision else None,
            "recent_logs": self.cycle_logs[-20:],
        }
