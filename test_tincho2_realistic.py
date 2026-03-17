#!/usr/bin/env python
"""Test Tincho2 tool calling with realistic (less explicit) prompts."""
import requests
import json

BASE_URL = "http://localhost:8001"
CHAT_ENDPOINT = f"{BASE_URL}/chat"

# Realistic prompts (less tool hints)
prompts = [
    {
        "name": "Realistic 1: Cambiar parámetro",
        "message": "Cambido el leverage a 15 para más agresividad",
        "expected_tool": "apply_parameters or text response"
    },
    {
        "name": "Realistic 2: Consulta de mercado",
        "message": "¿Cómo va Bitcoin ahora?",
        "expected_tool": "get_market_snapshot or text response"
    },
    {
        "name": "Realistic 3: Abrir trade",
        "message": "Me gustaría operar SOL si está bien configurado",
        "expected_tool": "either tool or text"
    }
]

print("=" * 80)
print("TINCHO2 REALISTIC PROMPTS TEST (Port 8001)")
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
        tool = data.get('toolUsed')
        print(f"🔧 Tool Used: {tool or 'None (text response)'}")
        print(f"📝 Reply: {data.get('reply', 'N/A')[:250]}")
        
        if data.get('paramsApplied'):
            print(f"✏️ Params: {json.dumps(data.get('paramsApplied'), indent=2)}")
            
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

print(f"\n{'═' * 80}")
print("Analysis: If LLM uses tools naturally, tool calling is production-ready")
print(f"{'═' * 80}")
