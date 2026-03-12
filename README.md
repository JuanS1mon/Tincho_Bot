# Tincho Bot

Autonomous crypto futures trading agent (Binance testnet + DeepSeek/LLM) with
configurable AI-driven risk management and parameters.

## 🛠️ Preparativos iniciales

1. **Clonar el repositorio** y situarse en la carpeta:

   ```powershell
   git clone https://github.com/JuanS1mon/Tincho_Bot.git
   cd Tincho-Bot
   ```

2. **Crear y activar entorno virtual** (PowerShell):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Instalar dependencias**:

   ```powershell
   pip install -r requirements.txt
   ```

4. **Actualizar pip** (opcional pero recomendado):

   ```powershell
   python -m pip install --upgrade pip
   ```

## 🔐 Configuración de entorno

Editar `.env` con las claves apropiadas:

```dotenv
# BINANCE (testnet)
BINANCE_API_KEY=<tu_key>
BINANCE_SECRET_KEY=<tu_secret>
BINANCE_TESTNET=true

# IA (DeepSeek/OpenAI)
AI_PROVIDER=deepseek
AI_MODEL=deepseek-chat
AI_API_KEY=<tu_key>
AI_BASE_URL=https://api.deepseek.com

# TRADING
INITIAL_CAPITAL=100
SYMBOLS_CSV=BTCUSDT,ETHUSDT
LEVERAGE=3
MAX_CAPITAL_PER_TRADE=0.30
RISK_PER_TRADE=0.01
STOP_LOSS=0.02
TAKE_PROFIT=0.06
TIMEFRAME=15m
ANALYSIS_INTERVAL_SECONDS=900

# MONGO
MONGO_URI=mongodb://localhost:27017
MONGO_DB_NAME=tincho_bot

# API HTTP
API_HOST=0.0.0.0
API_PORT=8000
```

Además de `.env`, **`agente.md`** contiene la definición del prompt, límites
y reglas. Edita ese archivo para cambiar la estrategia o ajustar rangos de IA.

## ✅ Verificar configuración

```powershell
python app/main.py --check-config
```


## ▶️ Ejecutar el agente

- Dry‑run (sin enviar órdenes):

  ```powershell
  python app/main.py --dry-run
  ```

- **Simulación de 1 hora** (ciclo cada 60s, ~60 análisis, sin dinero real):

  ```powershell
  python app/main.py --dry-run --interval 60
  ```

  Mientras corre, en otra terminal podés monitorear:

  ```powershell
  # Ver logs en tiempo real
  Get-Content logs\trading.log -Wait -Tail 20

  # Ver portafolio simulado
  Invoke-RestMethod http://localhost:8000/portfolio | ConvertTo-Json
  ```

- Trading real en testnet:

  ```powershell
  python app/main.py --live
  ```

  > **Nota sobre listado blanco de IP:**
  > Binance Testnet registra como origen de las peticiones sus propios
  > servidores (por ejemplo `3.172.x.x`, `190.57.x.x`). Si habilitas
  > restricciones de IP en tu clave de API, **no agregues tu IP local**,
  > en su lugar desactiva la restricción o agrega las direcciones mostradas
  > en los errores. De lo contrario recibirás
  > `APIError(code=-2015): Invalid API-key, IP, or permissions for action`.

- Sin API HTTP (modo silencioso):

  ```powershell
  python app/main.py --live --no-api
  ```


## 📡 Monitoreo via HTTP

| Endpoint | Descripción |
|----------|-------------|
| `/agent/status` | Estado general del agente |
| `/portfolio` | Capital, PnL y win rate |
| `/positions` | Posiciones abiertas |
| `/market-analysis` | Datos de mercado por símbolo |
| `/logs?lines=N` | Últimas N líneas de log |
| `/trades?limit=N` | Últimos N trades |


## 🔄 Ajustes en caliente

- Modifica `agente.md` y llama a:

  ```python
  from config.agent_config import agent_config
  agent_config.reload()
  ```

- Para resetear parámetros IA:

  ```powershell
  .\.venv\Scripts\python.exe - <<'PY'
  from storage.database import db_manager
  db_manager.db['agent_states'].delete_one({'_id':'dynamic_parameters'})
  print('Parametros reseteados')
  PY
  ```

## 🧾 Utilidades

- Ver logs:

  ```powershell
  Get-Content logs\trading.log -Wait -Tail 50
  ```

- Para cambiar dependencias:

  1. Edita `requirements.txt`.
  2. Ejecuta: `pip install -r requirements.txt`.


## 📌 Consejos

- Usa always `--dry-run` tras cada modificación importante.
- El capital se reparte 50%/50% entre BTC y ETH automáticamente.
- Ajusta `agente.md` para evitar alucinaciones y fijar reglas duras.
- El comportamiento del agente se documenta en `agente.md`.

¡Disfruta operando con Tincho Bot!