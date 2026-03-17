"""Capital optimizer con guardas de estabilidad para evitar cierres por ruido."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config.logger import trading_logger as logger
from config.settings import settings


@dataclass
class PositionPerformance:
    symbol: str
    direction: str
    unrealized_pnl: float
    unrealized_pnl_pct: float
    capital_used: float
    entry_price: float
    current_price: float
    quantity: float


@dataclass
class ReallocationRecommendation:
    should_reallocate: bool
    worst_symbol: Optional[str] = None
    best_symbol: Optional[str] = None
    pnl_divergence: float = 0.0
    net_edge_pct: float = 0.0
    capital_to_move: float = 0.0
    reason: str = ""


class CapitalOptimizerTool:
    """Evalua si conviene cerrar la peor posicion y reasignar capital."""

    def __init__(
        self,
        enabled: bool = True,
        min_pnl_divergence_pct: float = 4.0,
        check_interval_cycles: int = 5,
        min_capital_to_reallocate: float = 10.0,
        confirm_cycles: int = 3,
        fee_slippage_pct: float = 0.35,
        min_net_edge_pct: float = 0.8,
    ) -> None:
        self.enabled = enabled
        self.min_pnl_divergence_pct = min_pnl_divergence_pct
        self.check_interval_cycles = check_interval_cycles
        self.min_capital_to_reallocate = min_capital_to_reallocate
        self.confirm_cycles = confirm_cycles
        self.fee_slippage_pct = fee_slippage_pct
        self.min_net_edge_pct = min_net_edge_pct
        self.cycle_counter = 0
        self._prev_best: Optional[str] = None
        self._prev_worst: Optional[str] = None
        self._best_streak = 0
        self._worst_streak = 0

    def analyze_positions(self, positions: Dict[str, Any]) -> ReallocationRecommendation:
        if not self.enabled:
            return ReallocationRecommendation(should_reallocate=False, reason="disabled")

        self.cycle_counter += 1
        if self.cycle_counter % self.check_interval_cycles != 0:
            return ReallocationRecommendation(should_reallocate=False, reason="await_cycle")

        if not positions or len(positions) < 2:
            return ReallocationRecommendation(should_reallocate=False, reason="insufficient_positions")

        perfs = self._extract_performances(positions)
        if len(perfs) < 2:
            return ReallocationRecommendation(should_reallocate=False, reason="not_enough_open_positions")

        best_perf = max(perfs, key=lambda p: p.unrealized_pnl_pct)
        worst_perf = min(perfs, key=lambda p: p.unrealized_pnl_pct)
        divergence = best_perf.unrealized_pnl_pct - worst_perf.unrealized_pnl_pct

        self._update_streaks(best_perf.symbol, worst_perf.symbol)

        # Regla extra (punto 3): confirmar por varios ciclos antes de cerrar la perdedora.
        if self._best_streak < self.confirm_cycles or self._worst_streak < self.confirm_cycles:
            return ReallocationRecommendation(
                should_reallocate=False,
                reason=f"await_confirmation best={self._best_streak}/{self.confirm_cycles} worst={self._worst_streak}/{self.confirm_cycles}",
                best_symbol=best_perf.symbol,
                worst_symbol=worst_perf.symbol,
                pnl_divergence=divergence,
            )

        net_edge = divergence - self.fee_slippage_pct
        logger.info(
            "[CapOptimizer] best=%s(%.2f%%) worst=%s(%.2f%%) div=%.2f%% net=%.2f%% streak=%d/%d",
            best_perf.symbol,
            best_perf.unrealized_pnl_pct,
            worst_perf.symbol,
            worst_perf.unrealized_pnl_pct,
            divergence,
            net_edge,
            self._best_streak,
            self._worst_streak,
        )

        if worst_perf.capital_used < self.min_capital_to_reallocate:
            return ReallocationRecommendation(
                should_reallocate=False,
                reason=f"capital_below_min_{worst_perf.capital_used:.2f}",
                best_symbol=best_perf.symbol,
                worst_symbol=worst_perf.symbol,
                pnl_divergence=divergence,
                net_edge_pct=net_edge,
            )

        if divergence < self.min_pnl_divergence_pct:
            return ReallocationRecommendation(
                should_reallocate=False,
                reason=f"divergence_below_threshold_{divergence:.2f}",
                best_symbol=best_perf.symbol,
                worst_symbol=worst_perf.symbol,
                pnl_divergence=divergence,
                net_edge_pct=net_edge,
            )

        if net_edge < self.min_net_edge_pct:
            return ReallocationRecommendation(
                should_reallocate=False,
                reason=f"net_edge_below_threshold_{net_edge:.2f}",
                best_symbol=best_perf.symbol,
                worst_symbol=worst_perf.symbol,
                pnl_divergence=divergence,
                net_edge_pct=net_edge,
            )

        return ReallocationRecommendation(
            should_reallocate=True,
            worst_symbol=worst_perf.symbol,
            best_symbol=best_perf.symbol,
            pnl_divergence=divergence,
            net_edge_pct=net_edge,
            capital_to_move=worst_perf.capital_used,
            reason=f"confirmed_divergence_{divergence:.2f}_net_{net_edge:.2f}",
        )

    def _update_streaks(self, best_symbol: str, worst_symbol: str) -> None:
        if best_symbol == self._prev_best:
            self._best_streak += 1
        else:
            self._best_streak = 1
            self._prev_best = best_symbol

        if worst_symbol == self._prev_worst:
            self._worst_streak += 1
        else:
            self._worst_streak = 1
            self._prev_worst = worst_symbol

    def _extract_performances(self, positions: Dict[str, Any]) -> List[PositionPerformance]:
        perfs: List[PositionPerformance] = []
        for symbol, pos in positions.items():
            if not pos:
                continue
            try:
                perfs.append(
                    PositionPerformance(
                        symbol=symbol,
                        direction=getattr(pos, "direction", "UNKNOWN"),
                        unrealized_pnl=getattr(pos, "unrealized_pnl", 0.0),
                        unrealized_pnl_pct=getattr(pos, "unrealized_pnl_pct", 0.0),
                        capital_used=getattr(pos, "capital_used", 0.0),
                        entry_price=getattr(pos, "entry_price", 0.0),
                        current_price=getattr(pos, "current_price", 0.0),
                        quantity=getattr(pos, "quantity", 0.0),
                    )
                )
            except Exception as exc:
                logger.error("[CapOptimizer] Error extrayendo perf de %s: %s", symbol, exc)
        return perfs

    def get_statistics(self, positions: Dict[str, Any]) -> Dict[str, Any]:
        perfs = self._extract_performances(positions)
        if not perfs:
            return {
                "total_positions": 0,
                "avg_pnl_pct": 0.0,
                "best_symbol": None,
                "best_pnl_pct": 0.0,
                "worst_symbol": None,
                "worst_pnl_pct": 0.0,
                "divergence": 0.0,
                "total_capital_invested": 0.0,
            }

        best = max(perfs, key=lambda p: p.unrealized_pnl_pct)
        worst = min(perfs, key=lambda p: p.unrealized_pnl_pct)
        avg = sum(p.unrealized_pnl_pct for p in perfs) / len(perfs)
        total_capital = sum(p.capital_used for p in perfs)

        return {
            "total_positions": len(perfs),
            "avg_pnl_pct": avg,
            "best_symbol": best.symbol,
            "best_pnl_pct": best.unrealized_pnl_pct,
            "worst_symbol": worst.symbol,
            "worst_pnl_pct": worst.unrealized_pnl_pct,
            "divergence": best.unrealized_pnl_pct - worst.unrealized_pnl_pct,
            "total_capital_invested": total_capital,
        }


capital_optimizer = CapitalOptimizerTool(
    enabled=settings.capital_reallocation_enabled,
    min_pnl_divergence_pct=settings.capital_reallocation_min_divergence_pct,
    check_interval_cycles=settings.capital_reallocation_check_interval_cycles,
    min_capital_to_reallocate=settings.capital_reallocation_min_amount,
    confirm_cycles=settings.capital_reallocation_confirm_cycles,
    fee_slippage_pct=settings.capital_reallocation_fee_slippage_pct,
    min_net_edge_pct=settings.capital_reallocation_min_net_edge_pct,
)
