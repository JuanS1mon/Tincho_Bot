"""
tests/test_capital_optimizer.py
===============================
Tests para el Capital Optimizer Tool.
"""
import pytest
from dataclasses import dataclass
from tools.capital_optimizer_tool import CapitalOptimizerTool


@dataclass
class MockPosition:
    """Mock Position para testing."""
    symbol: str
    direction: str
    unrealized_pnl: float
    unrealized_pnl_pct: float
    capital_used: float
    entry_price: float
    current_price: float
    quantity: float


def test_capital_optimizer_no_realloc_when_disabled():
    """No reallocar si está desactivado."""
    optimizer = CapitalOptimizerTool(enabled=False)
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=60.0, unrealized_pnl_pct=5.0,
            capital_used=1200.0, entry_price=43000, current_price=45000, quantity=0.0278
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }
    
    rec = optimizer.analyze_positions(positions)
    assert not rec.should_reallocate


def test_capital_optimizer_detects_divergence():
    """Detecta divergencia de rendimiento entre posiciones."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=4.0,
        check_interval_cycles=1,
        min_capital_to_reallocate=10.0,
        confirm_cycles=1,
        fee_slippage_pct=0.0,
        min_net_edge_pct=0.0,
    )
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=60.0, unrealized_pnl_pct=5.0,  # Mejor
            capital_used=1200.0, entry_price=43000, current_price=45000, quantity=0.0278
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,  # Peor (5% - 1% = 4%)
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }
    
    rec = optimizer.analyze_positions(positions)
    assert rec.should_reallocate
    assert rec.worst_symbol == "ETHUSDT"
    assert rec.best_symbol == "BTCUSDT"
    assert abs(rec.pnl_divergence - 4.0) < 0.01


def test_capital_optimizer_no_realloc_below_threshold():
    """No reallocar si divergencia < umbral."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=5.0,  # Umbral alto
        check_interval_cycles=1,
        min_capital_to_reallocate=10.0,
        confirm_cycles=1,
        fee_slippage_pct=0.0,
        min_net_edge_pct=0.0,
    )
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=60.0, unrealized_pnl_pct=5.0,
            capital_used=1200.0, entry_price=43000, current_price=45000, quantity=0.0278
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,  # Solo 4% de diferencia
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }
    
    rec = optimizer.analyze_positions(positions)
    assert not rec.should_reallocate


def test_capital_optimizer_no_realloc_insufficient_capital():
    """No reallocar si capital < mínimo."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=4.0,
        check_interval_cycles=1,
        min_capital_to_reallocate=50.0,  # Umbral alto
        confirm_cycles=1,
        fee_slippage_pct=0.0,
        min_net_edge_pct=0.0,
    )
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=60.0, unrealized_pnl_pct=5.0,
            capital_used=1200.0, entry_price=43000, current_price=45000, quantity=0.0278
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,
            capital_used=10.0, entry_price=2500, current_price=2525, quantity=0.004  # Capital pequeño
        ),
    }
    
    rec = optimizer.analyze_positions(positions)
    assert not rec.should_reallocate  # No reallocar capital insuficiente


def test_capital_optimizer_statistics():
    """Calcula estadísticas de rendimiento."""
    optimizer = CapitalOptimizerTool()
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=60.0, unrealized_pnl_pct=6.0,
            capital_used=1000.0, entry_price=43000, current_price=45000, quantity=0.0233
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
        "XAUUSDT": MockPosition(
            symbol="XAUUSDT", direction="SHORT",
            unrealized_pnl=-5.0, unrealized_pnl_pct=-0.5,
            capital_used=1000.0, entry_price=2450, current_price=2445, quantity=0.408
        ),
    }
    
    stats = optimizer.get_statistics(positions)
    
    assert stats["total_positions"] == 3
    assert stats["best_symbol"] == "BTCUSDT"
    assert stats["best_pnl_pct"] == 6.0
    assert stats["worst_symbol"] == "XAUUSDT"
    assert stats["worst_pnl_pct"] == -0.5
    assert abs(stats["divergence"] - 6.5) < 0.01


def test_capital_optimizer_checks_interval():
    """Respeta el intervalo de chequeo."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=1.0,  # Bajo para que se detecte cualquier divergencia
        check_interval_cycles=5,  # Revisar cada 5 ciclos
        min_capital_to_reallocate=10.0,
        confirm_cycles=1,
        fee_slippage_pct=0.0,
        min_net_edge_pct=0.0,
    )
    
    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=50.0, unrealized_pnl_pct=5.0,
            capital_used=1000.0, entry_price=43000, current_price=45000, quantity=0.0233
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }
    
    # Primeros 4 ciclos no deberían reallocar
    for i in range(4):
        rec = optimizer.analyze_positions(positions)
        assert not rec.should_reallocate, f"No debería reallocar en ciclo {i+1}"
    
    # Quinto ciclo sí
    rec = optimizer.analyze_positions(positions)
    assert rec.should_reallocate, "Debería reallocar en ciclo 5"


def test_capital_optimizer_requires_confirmation_cycles():
    """No cierra la perdedora hasta confirmar N ciclos consecutivos."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=1.0,
        check_interval_cycles=1,
        min_capital_to_reallocate=10.0,
        confirm_cycles=3,
        fee_slippage_pct=0.0,
        min_net_edge_pct=0.0,
    )

    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=50.0, unrealized_pnl_pct=5.0,
            capital_used=1000.0, entry_price=43000, current_price=45000, quantity=0.0233
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=10.0, unrealized_pnl_pct=1.0,
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }

    rec1 = optimizer.analyze_positions(positions)
    rec2 = optimizer.analyze_positions(positions)
    rec3 = optimizer.analyze_positions(positions)

    assert not rec1.should_reallocate
    assert not rec2.should_reallocate
    assert rec3.should_reallocate


def test_capital_optimizer_blocks_when_net_edge_is_too_low():
    """No reallocar si la ventaja neta (divergencia - costos) no alcanza."""
    optimizer = CapitalOptimizerTool(
        enabled=True,
        min_pnl_divergence_pct=2.0,
        check_interval_cycles=1,
        min_capital_to_reallocate=10.0,
        confirm_cycles=1,
        fee_slippage_pct=3.7,
        min_net_edge_pct=0.5,
    )

    positions = {
        "BTCUSDT": MockPosition(
            symbol="BTCUSDT", direction="LONG",
            unrealized_pnl=50.0, unrealized_pnl_pct=5.0,
            capital_used=1000.0, entry_price=43000, current_price=45000, quantity=0.0233
        ),
        "ETHUSDT": MockPosition(
            symbol="ETHUSDT", direction="LONG",
            unrealized_pnl=20.0, unrealized_pnl_pct=1.5,
            capital_used=1000.0, entry_price=2500, current_price=2525, quantity=0.4
        ),
    }

    rec = optimizer.analyze_positions(positions)
    assert not rec.should_reallocate
    assert "net_edge_below_threshold" in rec.reason


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
