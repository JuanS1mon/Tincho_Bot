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

### Simulación (recomendado antes de operar con dinero real)

Corre el agente con datos de mercado reales de Binance testnet pero **sin
ejecutar ninguna orden**. El capital es ficticio (el valor de `INITIAL_CAPITAL`
en `.env`).

```powershell
# Simulación estándar — 1 ciclo cada 15 minutos (igual que producción)
python app/main.py --dry-run

# Simulación rápida — 1 ciclo por minuto (~60 análisis en 1 hora)
python app/main.py --dry-run --interval 60

# Simulación ultra-rápida — 1 ciclo cada 30 segundos
python app/main.py --dry-run --interval 30
```

El flag `--interval SEGUNDOS` acepta cualquier valor y **siempre tiene
prioridad** sobre el intervalo guardado en MongoDB por la IA.

### Monitoreo durante la simulación

Mientras corre `--dry-run`, abre **otra terminal** y usa:

```powershell
# Ver logs en tiempo real (se actualiza solo):
Get-Content logs\trading.log -Wait -Tail 20

# Ver portafolio simulado (capital, PnL, win rate):
Invoke-RestMethod http://localhost:8000/portfolio | ConvertTo-Json

# Ver trades simulados ejecutados:
Invoke-RestMethod "http://localhost:8000/trades?limit=20" | ConvertTo-Json -Depth 5

# Ver análisis de mercado por símbolo (precio, RSI, tendencia):
Invoke-RestMethod http://localhost:8000/market-analysis | ConvertTo-Json -Depth 5

# Ver estado general del agente:
Invoke-RestMethod http://localhost:8000/agent/status | ConvertTo-Json
```

### Trading real en testnet

Una vez validada la simulación, podés operar con la cuenta testnet de Binance
(sin dinero real, pero con órdenes reales):

```powershell
python app/main.py --live
```

### Sin API HTTP (modo silencioso)

```powershell
python app/main.py --live --no-api
```

### Detener el agente

Presiona `Ctrl+C` en la terminal donde corre el bot. El apagado es graceful
(cierra posiciones pendientes y guarda el estado en MongoDB).



## �️ Dashboard Web (Next.js)

El proyecto incluye un dashboard visual en `frontend/` que se conecta
automáticamente a la API del bot y se actualiza cada 5 segundos.

**Requisitos**: Node.js 18+ instalado.

```powershell
# Primera vez — instalar dependencias:
cd frontend
npm install

# Iniciar el dashboard (mientras el bot corre en otra terminal):
npm run dev
```

Luego abrir **http://localhost:3000** en el navegador.

| Panel | Contenido |
|-------|-----------|
| Header | Estado del agente (ANALYZING/IDLE/ERROR), ciclo #, DRY-RUN/LIVE |
| Portafolio | Capital, PnL acumulado, win rate, posiciones abiertas |
| Posiciones | Entrada, SL, TP, cantidad, capital por posición |
| Análisis de mercado | Precio, tendencia, RSI, SMA20/50, señal por símbolo |
| Historial | Últimos 20 trades con PnL, dirección y duración |

> Si el bot no está corriendo, el dashboard muestra un banner de "offline" con las instrucciones para iniciarlo.

---

## �📡 Monitoreo via HTTP

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