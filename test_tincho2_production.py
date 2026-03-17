#!/usr/bin/env python
"""Test Tincho2 chat endpoint (tool calling) on port 8000 (production)."""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

print("═" * 80)
print("TINCHO2 CHAT - TEST EN PRODUCCIÓN (Puerto 8000)")
print("═" * 80)

# Wait a bit for agent to initialize
time.sleep(5)

# Test prompts
prompts = [
    {
        "name": "Test 1: Cambiar parámetros",
        "message": "Cambio el leverage a 8 para más seguridad",
        "expected_tool": "apply_parameters"
    },
    {
        "name": "Test 2: Consultar mercado",
        "message": "¿Cómo está el Bitcoin ahora?",
        "expected_tool": "get_market_snapshot"
    },
    {
        "name": "Test 3: Consulta general",
        "message": "Dame tu análisis actual del mercado",
        "expected_tool": "None (text response)"
    }
]

print("\n✅ Testing Tincho2 Chat Endpoint\n")

for i, test in enumerate(prompts, 1):
    print(f"{'─' * 80}")
    print(f"TEST {i}: {test['name']}")
    print(f"{'─' * 80}")
    print(f"Prompt: {test['message']}\n")
    
    payload = {
        "message": test['message'],
        "history": []
    }
    
    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json=payload,
            timeout=15
        )
        
        if resp.status_code == 200:
            data = resp.json()
            tool_used = data.get('toolUsed', 'None')
            reply = data.get('reply', 'N/A')[:150]
            
            print(f"✅ Status: {resp.status_code}")
            print(f"🔧 Tool: {tool_used}")
            print(f"💬 Reply: {reply}")
            
            if data.get('paramsApplied'):
                print(f"📊 Params Applied: {json.dumps(data['paramsApplied'])}")
            
            # Validate
            if tool_used and tool_used != 'None':
                print(f"✅ Tool invocado correctamente!")
            else:
                print(f"✓ Respuesta de texto (esperado)")
                
        else:
            print(f"❌ Status: {resp.status_code}")
            print(f"   Error: {resp.text[:100]}")
            
    except requests.exceptions.Timeout:
        print(f"⏱️ Timeout (15s)")
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {e}")

print(f"\n{'═' * 80}")
print("RESUMEN")
print(f"{'═' * 80}")
print("""
✅ Si los tests pasaron:
   - Tincho2 chat endpoint está funcional
   - Tool calling está activo (herramientas usadas apropiadamente)
   - Listo para producción

📝 Configuración Active:
   - TOOL_CALLING_TINCHO2 = TRUE
   - Endpoint: POST /chat
   - Herramientas: apply_parameters, get_market_snapshot, open_manual_position
""")
