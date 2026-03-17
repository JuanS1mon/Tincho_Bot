"""
Test script for Ruben offline analysis with tool calling.
Validates generate_insights_report, select_profile, apply_recommendations.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from offline_agents.ruben_tool_calling_wrapper import RubenToolCallingWrapper
from config.settings import settings


def test_generate_insights_report():
    """Test generating a insights report."""
    print("\n" + "="*70)
    print("TEST 1: Generate Insights Report")
    print("="*70)
    
    wrapper = RubenToolCallingWrapper()
    
    result = wrapper.generate_insights_report(
        hours=24,
        symbols="BTCUSDT,ETHUSDT",
        analysis_type="simple"
    )
    
    print(f"Status: {result.get('status')}")
    print(f"Message: {result.get('message')}")
    
    if result.get('status') == 'success':
        report = result.get('report', {})
        print(f"\nReport Summary:")
        print(f"  - Hours analyzed: {report.get('hours')}")
        print(f"  - Total trades: {report.get('total_trades')}")
        print(f"  - Symbols: {report.get('symbols')}")
        print(f"  - Symbol count: {report.get('symbol_count')}")
        
        if report.get('stats'):
            print(f"\nPer-Symbol Stats:")
            for stat in report.get('stats', []):
                print(f"  {stat.get('symbol')}:")
                print(f"    - Trades: {stat.get('total_trades')}")
                print(f"    - Win rate: {stat.get('win_rate'):.2%}")
                print(f"    - Total PnL: ${stat.get('total_pnl'):.2f}")
                print(f"    - Avg PnL %: {stat.get('avg_pnl_pct'):.4f}")
                print(f"    - Profit factor: {stat.get('profit_factor'):.2f}")
                print(f"    - Max drawdown: {stat.get('max_drawdown_pct'):.2%}")
        
        if report.get('adjustments'):
            print(f"\nProposed Adjustments:")
            adj = report.get('adjustments', {})
            print(f"  - Status: {adj.get('summary')}")
            if adj.get('suggestions'):
                print(f"  - Suggestions:")
                for k, v in adj.get('suggestions', {}).items():
                    print(f"    {k}: {v}")
            if adj.get('rationale'):
                print(f"  - Rationale:")
                for r in adj.get('rationale', []):
                    print(f"    - {r}")
    else:
        print(f"Error: {result.get('message')}")


def test_select_profile():
    """Test selecting a profile (requires two-layer analysis)."""
    print("\n" + "="*70)
    print("TEST 2: Generate Two-Layer Insights and Select Profile")
    print("="*70)
    
    wrapper = RubenToolCallingWrapper()
    
    # First generate with two-layer analysis
    print("\nGenerating two-layer analysis...")
    result = wrapper.generate_insights_report(
        hours=24,
        symbols="BTCUSDT,ETHUSDT",
        analysis_type="two_layer"
    )
    
    if result.get('status') != 'success':
        print(f"Failed to generate report: {result.get('message')}")
        return
    
    report = result.get('report', {})
    layer2 = report.get('layer2', {})
    
    if not layer2:
        print("Two-layer analysis not available (likely missing AI API key)")
        print("Testing with simulated profile selection instead...")
        return
    
    print(f"\nLayer 2 Status: {layer2.get('status')}")
    print(f"Layer 2 Confidence: {layer2.get('confidence')}")
    
    # Now select a profile
    print("\nSelecting conservative profile...")
    select_result = wrapper.select_profile(
        profile="conservative",
        reasoning="Risk preservation given market volatility"
    )
    
    print(f"Selection Status: {select_result.get('status')}")
    if select_result.get('status') == 'success':
        profile = select_result.get('profile', {})
        print(f"Selected Profile: {profile.get('selected_profile')}")
        print(f"Selection Reasoning: {profile.get('selection_reasoning')}")
        if profile.get('adjustments'):
            print(f"Profile Adjustments:")
            for k, v in profile.get('adjustments', {}).items():
                print(f"  - {k}: {v}")
    else:
        print(f"Error: {select_result.get('message')}")


def test_apply_recommendations():
    """Test applying recommendations."""
    print("\n" + "="*70)
    print("TEST 3: Apply Recommendations")
    print("="*70)
    
    wrapper = RubenToolCallingWrapper()
    
    # Generate analysis first
    print("\nGenerating analysis...")
    result = wrapper.generate_insights_report(
        hours=24,
        symbols="BTCUSDT,ETHUSDT",
        analysis_type="simple"
    )
    
    if result.get('status') != 'success':
        print(f"Failed to generate report: {result.get('message')}")
        return
    
    # Try to apply (without two-layer, it might skip)
    print("\nApplying recommendations...")
    apply_result = wrapper.apply_recommendations(
        apply_profile="yes",
        confidence_threshold=0.5
    )
    
    print(f"Application Status: {apply_result.get('status')}")
    print(f"Message: {apply_result.get('message')}")
    if apply_result.get('adjustments'):
        print(f"Applied Adjustments:")
        print(json.dumps(apply_result.get('adjustments'), indent=2, default=str))


def test_skip_analysis():
    """Test skipping analysis."""
    print("\n" + "="*70)
    print("TEST 4: Skip Analysis")
    print("="*70)
    
    wrapper = RubenToolCallingWrapper()
    
    result = wrapper.skip_analysis(reason="Insufficient market data in selected window")
    
    print(f"Status: {result.get('status')}")
    print(f"Reason: {result.get('reason')}")
    print(f"Message: {result.get('message')}")


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("RUBEN OFFLINE ANALYSIS - TOOL CALLING TESTS")
    print("="*70)
    print(f"MongoDB: {settings.mongo_uri} / {settings.mongo_db_name}")
    print(f"AI Provider: {settings.ai_provider} ({settings.ai_model})")
    print(f"Tool Calling Enabled: {settings.tool_calling_ruben}")
    
    try:
        test_generate_insights_report()
        test_select_profile()
        test_apply_recommendations()
        test_skip_analysis()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
