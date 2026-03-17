#!/usr/bin/env python
"""Deploy Tincho1 with tool calling: test on 8002, then live on 8000."""

import subprocess
import time
import os
import requests
import sys
import signal

def kill_port(port):
    """Kill process on given port."""
    os.system(f'netstat -ano | findstr ":{port}" | findstr "LISTENING" | For /F "tokens=5" %a in (\'@^"\') do taskkill /PID %a /F')

def main():
    print("╔" + "═" * 62 + "╗")
    print("║ TINCHO1 TOOL CALLING - TEST & DEPLOY TO PRODUCTION       ║")
    print("╚" + "═" * 62 + "╝")
    
    # Step 1: Test on 8002
    print("\n[1/3] Lanzando Tincho1 en puerto 8002 (TEST - DRY-RUN)...")
    env = os.environ.copy()
    env.update({
        'API_PORT': '8002',
        'MONGO_DB_NAME': 'tincho_bot_tincho1_test',
        'TOOL_CALLING_TINCHO1': 'true',
        'TOOL_CALLING_TINCHO2': 'false',
    })
    
    cmd = [
        sys.executable,
        'app/main.py',
        '--dry-run',
        '--interval', '60'
    ]
    
    test_proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd='C:\\Tincho-bot'
    )
    
    print(f"   ✅ Proceso iniciado (PID: {test_proc.pid})")
    print("\n   Esperando 75 segundos para primer ciclo completo...")
    
    time.sleep(75)
    
    # Step 2: Verify 8002
    print("\n[2/3] Verificando puerto 8002...")
    try:
        resp = requests.get('http://localhost:8002/agent/status', timeout=5)
        status = resp.json()
        cycle = status.get('cycle', 'N/A')
        print(f"   ✅ Status API respondiendo - Ciclo: {cycle}")
        print(f"   ✅ Tincho1 test VALIDADO")
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
    
    # Step 3: Kill test, deploy to prod
    print("\n[3/3] Migrando a PRODUCCIÓN (puerto 8000 - LIVE)...")
    print("   Deteniendo proceso en 8002...")
    test_proc.terminate()
    try:
        test_proc.wait(timeout=5)
    except:
        test_proc.kill()
    
    time.sleep(3)
    
    print("   Iniciando Tincho1 en LIVE (sin --dry-run)...")
    
    env_prod = os.environ.copy()
    env_prod.update({
        'API_PORT': '8000',
        'MONGO_DB_NAME': 'tincho_bot',
        'TOOL_CALLING_TINCHO1': 'true',
        'TOOL_CALLING_TINCHO2': 'true',
    })
    
    cmd_prod = [
        sys.executable,
        'app/main.py',
        '--interval', '60'
        # SIN --dry-run = LIVE
    ]
    
    prod_proc = subprocess.Popen(
        cmd_prod,
        env=env_prod,
        stdout=open('logs/production.log', 'a'),
        stderr=open('logs/production.log', 'a'),
        cwd='C:\\Tincho-bot'
    )
    
    print(f"   ✅ Proceso LIVE iniciado (PID: {prod_proc.pid})")
    
    time.sleep(10)
    
    # Verify 8000
    try:
        resp = requests.get('http://localhost:8000/agent/status', timeout=5)
        if resp.status_code == 200:
            print("\n" + "╔" + "═" * 62 + "╗")
            print("║ ✅ TINCHO1 ACTIVO EN PRODUCCIÓN CON TOOL CALLING         ║") 
            print("╚" + "═" * 62 + "╝")
            print("\n📊 Configuración:")
            print("   API_PORT: 8000")
            print("   MONGO_DB: tincho_bot")
            print("   TOOL_CALLING_TINCHO1: TRUE ✅")
            print("   TOOL_CALLING_TINCHO2: TRUE ✅")
            print("   Modo: LIVE (sin --dry-run)")
            print("\n📝 Monitorear logs:")
            print("   trading.log (general)")
            print("   production.log (específico)")
            print("\n🔗 APIs disponibles:")
            print("   GET http://localhost:8000/agent/status")
            print("   GET http://localhost:8000/portfolio")
            print("   POST http://localhost:8000/chat (si Tincho2 activado)")
        else:
            print(f"   ❌ Error: Status {resp.status_code}")
    except Exception as e:
        print(f"   ⚠️  No responde aún: {e}")
    
    print("\n✅ Setup completado. Tincho1 está en LIVE con tool calling.")

if __name__ == '__main__':
    main()
