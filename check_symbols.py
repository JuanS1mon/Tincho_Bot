#!/usr/bin/env python
"""Inspect configured symbols."""
import requests
import json

print("=" * 70)
print("API STATUS CHECK (Port 8001)")
print("=" * 70)

try:
    resp = requests.get("http://localhost:8001/agent/status", timeout=5)
    if resp.status_code == 200:
        status = resp.json()
        print("\n✅ Agent Status Retrieved")
        
        # Market snapshots
        snaps = status.get('state', {}).get('market_snapshots', {})
        if snaps:
            symbols = list(snaps.keys())
            print(f"\n📊 Available Symbols ({len(symbols)}): {symbols[:10]}")
        else:
            print("\n⚠️ No market snapshots yet")
        
        # Last analysis
        last_analysis = status.get('last_analysis', {})
        print(f"\n🔍 Last Analysis Keys: {list(last_analysis.keys())[:5]}")
        
    else:
        print(f"❌ Status code: {resp.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")

# Also check portfolio to see monitored assets
print("\n" + "=" * 70)
print("PORTFOLIO STATUS")
print("=" * 70)

try:
    resp = requests.get("http://localhost:8001/portfolio", timeout=5)
    if resp.status_code == 200:
        portfolio = resp.json()
        positions = portfolio.get('positions', {})
        print(f"\n📈 Open Positions: {list(positions.keys()) or 'None'}")
    else:
        print(f"❌ Status code: {resp.status_code}")
except Exception as e:
    print(f"❌ Error: {e}")
