#!/usr/bin/env python
"""Test script for Tincho2 tool calling on port 8001."""
import requests
import json

BASE_URL = "http://localhost:8001"
CHAT_ENDPOINT = f"{BASE_URL}/chat"

# Test prompts
prompts = [
    {
        "name": "Prompt 1: Cambiar leverage",
        "message": "cambia leverage a 12",
        "expected_tool": "apply_parameters"
    },
    {
        "name": "Prompt 2: Ver análisis de BTC",
        "message": "quiero ver el análisis de BTC",
        "expected_tool": "get_market_snapshot"
    },
    {
        "name": "Prompt 3: Abrir posición en PEPE LONG",
        "message": "entra en PEPEUSDT LONG",
        "expected_tool": "open_manual_position"
    }
]

for i, test in enumerate(prompts, 1):
    print(f"\n{'='*70}")
    print(f"TEST {i}: {test['name']}")
    print(f"{'='*70}")
    
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
        print(f"📝 Reply: {data.get('reply', 'N/A')[:200]}")
        print(f"🔧 Tool usado: {data.get('toolUsed', 'None')}")
        print(f"✏️ Params aplicados: {data.get('paramsApplied', 'N/A')}")
        
        # Verificar tool esperada
        tool_used = data.get('toolUsed')
        if tool_used == test['expected_tool']:
            print(f"✅ Tool coincide con lo esperado: {test['expected_tool']}")
        elif tool_used:
            print(f"⚠️ Tool usada: {tool_used}, esperada: {test['expected_tool']}")
        else:
            print(f"⚠️ Ninguna tool usada, esperada: {test['expected_tool']}")
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Error de conexión: {e}")
    except requests.exceptions.Timeout:
        print(f"❌ Timeout (15s)")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

print(f"\n{'='*70}")
print("Tests completados")
print(f"{'='*70}")
