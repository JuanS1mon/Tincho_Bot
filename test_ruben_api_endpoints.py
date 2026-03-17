"""
Test script for Ruben API endpoints.
Assumes the main server is already running on port 8000.

Run with:
  python test_ruben_api.py
"""

import asyncio
import json
import httpx
from datetime import datetime

BASE_URL = "http://localhost:8000"
RUBEN_BASE = f"{BASE_URL}/api/ruben"

async def test_status():
    """Test GET /api/ruben/status"""
    print("\n" + "="*70)
    print("TEST 1: Get Ruben Status")
    print("="*70)
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{RUBEN_BASE}/status")
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Ruben Status: {data.get('status')}")
            print(f"Message: {data.get('message')}")
            print(f"Tool Calling Enabled: {data.get('tool_calling_enabled')}")
            print(f"Last Analysis Available: {data.get('last_analysis_available')}")
        else:
            print(f"Error: {response.text}")


async def test_generate_insights():
    """Test POST /api/ruben/generate-insights"""
    print("\n" + "="*70)
    print("TEST 2: Generate Insights Report")
    print("="*70)
    
    payload = {
        "hours": 24,
        "symbols": "BTCUSDT,ETHUSDT",
        "analysis_type": "simple"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RUBEN_BASE}/generate-insights",
            json=payload
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Message: {data.get('message')}")
            
            if data.get('status') == 'success':
                report = data.get('report', {})
                print(f"\nReport Details:")
                print(f"  Hours: {report.get('hours')}")
                print(f"  Total Trades: {report.get('total_trades')}")
                print(f"  Symbols: {report.get('symbols')}")
                
                if report.get('stats'):
                    print(f"\nSymbol Stats:")
                    for stat in report.get('stats', []):
                        print(f"  {stat.get('symbol')}:")
                        print(f"    - Trades: {stat.get('total_trades')}")
                        print(f"    - Win Rate: {stat.get('win_rate'):.2%}")
        else:
            print(f"Error: {response.text}")


async def test_two_layer_analysis():
    """Test POST /api/ruben/generate-insights with two_layer"""
    print("\n" + "="*70)
    print("TEST 3: Generate Two-Layer Analysis")
    print("="*70)
    
    payload = {
        "hours": 24,
        "symbols": "BTCUSDT,ETHUSDT",
        "analysis_type": "two_layer"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RUBEN_BASE}/generate-insights",
            json=payload,
            timeout=30.0  # Give extra time for LLM call
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            
            if data.get('status') == 'success':
                report = data.get('report', {})
                layer2 = report.get('layer2', {})
                
                if layer2:
                    print(f"Layer 2 Status: {layer2.get('status')}")
                    print(f"Layer 2 Confidence: {layer2.get('confidence')}")
                    print(f"Layer 2 Profiles Available: {list(layer2.get('profiles', {}).keys())}")
                else:
                    print("Layer 2 not available (check AI API key)")
        else:
            print(f"Error: {response.text}")


async def test_select_profile():
    """Test POST /api/ruben/select-profile"""
    print("\n" + "="*70)
    print("TEST 4: Select Profile")
    print("="*70)
    
    payload = {
        "profile": "conservative",
        "reasoning": "Risk preservation given current market conditions"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RUBEN_BASE}/select-profile",
            json=payload
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            if data.get('status') == 'success':
                profile = data.get('profile', {})
                print(f"Selected Profile: {profile.get('selected_profile')}")
                print(f"Selection Reasoning: {profile.get('selection_reasoning')}")
                if profile.get('adjustments'):
                    print(f"Adjustments:")
                    for k, v in profile.get('adjustments', {}).items():
                        print(f"  - {k}: {v}")
            else:
                print(f"Message: {data.get('message')}")
        else:
            print(f"Error: {response.text}")


async def test_skip_analysis():
    """Test POST /api/ruben/skip-analysis"""
    print("\n" + "="*70)
    print("TEST 5: Skip Analysis")
    print("="*70)
    
    payload = {
        "reason": "Insufficient recent trade data"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RUBEN_BASE}/skip-analysis",
            json=payload
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Status: {data.get('status')}")
            print(f"Reason: {data.get('reason')}")
            print(f"Message: {data.get('message')}")
        else:
            print(f"Error: {response.text}")


async def test_complete_flow():
    """Test POST /api/ruben/complete-flow"""
    print("\n" + "="*70)
    print("TEST 6: Complete Flow (Insights -> Profile -> Apply)")
    print("="*70)
    
    payload = {
        "hours": 24,
        "symbols": "BTCUSDT,ETHUSDT",
        "preferred_profile": "conservative",
        "auto_apply": False
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{RUBEN_BASE}/complete-flow",
            json=payload,
            timeout=30.0
        )
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Flow Status: {data.get('status')}")
            
            insights = data.get('insights', {})
            print(f"\nInsights Status: {insights.get('status')}")
            if insights.get('report'):
                print(f"  Total Trades: {insights['report'].get('total_trades')}")
            
            profile = data.get('profile_selection', {})
            print(f"\nProfile Selection Status: {profile.get('status')}")
            if profile.get('profile'):
                print(f"  Selected: {profile['profile'].get('selected_profile')}")
            
            application = data.get('application', {})
            print(f"\nApplication Status: {application.get('status')}")
            print(f"  Message: {application.get('message')}")
        else:
            print(f"Error: {response.text}")


async def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("RUBEN API ENDPOINT TESTS")
    print("="*70)
    print(f"API Base URL: {BASE_URL}")
    print(f"Ruben Base URL: {RUBEN_BASE}")
    print(f"Started at: {datetime.now().isoformat()}")
    
    try:
        # Test connectivity
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BASE_URL}/agent/status", timeout=5.0)
            if response.status_code != 200:
                print(f"\nERROR: Cannot connect to {BASE_URL}")
                print("Make sure the main server is running: python app/main.py")
                return
        
        # Run tests
        await test_status()
        await test_generate_insights()
        await test_two_layer_analysis()
        await test_select_profile()
        await test_skip_analysis()
        await test_complete_flow()
        
        print("\n" + "="*70)
        print("ALL TESTS COMPLETED")
        print("="*70)
        
    except Exception as e:
        print(f"\nTEST ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
