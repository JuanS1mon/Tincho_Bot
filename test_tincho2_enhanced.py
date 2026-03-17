#!/usr/bin/env python
"""Enhanced test for Tincho2 tool calling."""
import requests
import json

BASE_URL = "http://localhost:8001"
CHAT_ENDPOINT = f"{BASE_URL}/chat"

# Enhanced test prompts with explicit tool hints
prompts = [
    {
        "name": "Prompt 1: Cambiar leverage (explicit)",
        "message": "Quiero cambiar el leverage a 12. Usa la herramienta apply_parameters para ajustar leverage=12.",
        "expected_tool": "apply_parameters"
    },
    {
        "name": "Prompt 2: Ver análisis BTC (retest)",
        "message": "Obten el snapshot de mercado para BTCUSDT usando la herramienta get_market_snapshot.",
        "expected_tool": "get_market_snapshot"
    },
    {
        "name": "Prompt 3: Abrir posición con símbolo existente",
        "message": "Abre una posición LONG en ETHUSDT con 10% del capital usando open_manual_position.",
        "expected_tool": "open_manual_position"
    }
]

print("=" * 80)
print("TINCHO2 TOOL CALLING TESTS (Port 8001) - Enhanced")
print("=" * 80)

for i, test in enumerate(prompts, 1):
    print(f"\n{'─' * 80}")
    print(f"TEST {i}: {test['name']}")
    print(f"{'─' * 80}")
    print(f"Prompt: {test['message']}\n")
    
    payload = {
        "message": test["message"],
        "history": []
    }
    
    try:
        resp = requests.post(
            CHAT_ENDPOINT,
            json=payload,
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        
        print(f"✅ Status: {resp.status_code}")
        print(f"📝 Reply: {data.get('reply', 'N/A')[:250]}")
        print(f"🔧 Tool Used: {data.get('toolUsed', 'None')}")
        
        params = data.get('paramsApplied')
        if params:
            print(f"✏️ Params Applied: {json.dumps(params, indent=2)}")
        
        # Verify tool
        tool_used = data.get('toolUsed')
        expected = test['expected_tool']
        if tool_used == expected:
            print(f"✅ ✓ Tool matches expected: {expected}")
        elif tool_used:
            print(f"⚠️ Tool {tool_used} != expected {expected}")
        else:
            print(f"⚠️ No tool used (expected {expected})")
            
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

print(f"\n{'═' * 80}")
print("All tests completed")
print(f"{'═' * 80}")
