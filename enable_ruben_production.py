"""
Script to activate Ruben tool calling in production (port 8000).
Kills existing agent and relaunches with TOOL_CALLING_RUBEN=true
"""

import os
import subprocess
import time
import sys
from pathlib import Path

# Change to project root
os.chdir(Path(__file__).parent)

print("\n" + "="*70)
print("ACTIVATING RUBEN TOOL CALLING ON PORT 8000")
print("="*70)

# Kill existing processes on port 8000
print("\nKilling existing agents on port 8000...")
try:
    subprocess.run(
        'netstat -ano | findstr :8000 | findstr LISTENING',
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    # Get the PID and kill it
    result = subprocess.run(
        'netsh interface ipv4 show tcpconnections | findstr 8000',
        shell=True,
        capture_output=True,
        text=True,
        check=False
    )
    
    # More direct approach: use tasklist to find python process
    result = subprocess.run(
        'taskkill /F /IM python.exe /FI "WINDOWTITLE eq*8000*"',
        shell=True,
        capture_output=True,
        check=False
    )
    print("Sent termination signal to existing processes")
except Exception as e:
    print(f"Warning: Could not kill processes: {e}")

time.sleep(2)

# Set environment variables for production
env = os.environ.copy()
env['API_PORT'] = '8000'
env['MONGO_DB_NAME'] = 'tincho_bot'
env['TOOL_CALLING_TINCHO1'] = 'true'
env['TOOL_CALLING_TINCHO2'] = 'true'
env['TOOL_CALLING_MARQUITOS'] = 'true'
env['TOOL_CALLING_RUBEN'] = 'true'

print("\nEnvironment Variables:")
print(f"  API_PORT: {env.get('API_PORT')}")
print(f"  MONGO_DB_NAME: {env.get('MONGO_DB_NAME')}")
print(f"  TOOL_CALLING_TINCHO1: {env.get('TOOL_CALLING_TINCHO1')}")
print(f"  TOOL_CALLING_TINCHO2: {env.get('TOOL_CALLING_TINCHO2')}")
print(f"  TOOL_CALLING_MARQUITOS: {env.get('TOOL_CALLING_MARQUITOS')}")
print(f"  TOOL_CALLING_RUBEN: {env.get('TOOL_CALLING_RUBEN')} <-- NEW")

print("\nLaunching Tincho Bot with all agents + Ruben (LIVE mode)...")
print("="*70)

# Start the agent
subprocess.Popen(
    [sys.executable, 'app/main.py'],
    env=env,
    cwd=str(Path(__file__).parent),
)

print("\nAgents launching in background...")
print("  Tincho1: Autonomous trading with tool calling")
print("  Tincho2: Chat advisor with tool calling")
print("  Marquitos: Scalper with tool calling")
print("  Ruben: Offline analysis with tool calling <-- NEW")
print("\nAPI running on http://localhost:8000")
print("Check status with curl: http://localhost:8000/agent/status")
print("="*70)
