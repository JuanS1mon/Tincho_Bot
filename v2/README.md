# Tincho Bot v2 (minimal)

Objetivo: reconstruir una base simple, auditable y medible.

## Reglas iniciales

- Un solo simbolo al inicio (BTCUSDT).
- Una sola estrategia.
- Maximo 1 posicion abierta.
- Riesgo fijo por trade.
- SL/TP fijos (sin capas dinamicas de salida al inicio).
- Sin learning automatico en caliente.
- Sin reallocacion de capital.

## Lecciones aplicadas desde v1

- Evitar overrides agresivos que ignoran bloqueos de riesgo.
- Evitar cierre de "profit lock" sobre micro-ganancias que no cubren fees.
- Reducir complejidad: cada regla debe ser explicable en una linea.
- Medir siempre en neto (incluyendo comisiones) y con diarios reproducibles.

## Componentes

- `config.py`: parametros estaticos del motor.
- `strategy.py`: estrategia unica (EMA + RSI).
- `risk.py`: sizing fijo por riesgo con tope de notional.
- `backtest.py`: backtester sencillo OHLCV con fees.
- `run_backtest.py`: runner CLI para csv.

## CSV esperado

Columnas requeridas:

- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`

## Ejecucion

```bash
python -m v2.prepare_data --symbol BTCUSDT --interval 15m --limit 1000 --out v2/data_btcusdt_15m.csv
python -m v2.run_backtest --csv data.csv
```

## Runner continuo (paper)

Para que corra como el bot anterior (ciclos continuos):

```bash
python -m v2.live_runner --symbols ETHUSDT,BTCUSDT --interval 15m --equity 100 --poll-seconds 30
```

Con `--symbols ETHUSDT,BTCUSDT` y `--equity 100`, el runner divide el capital en partes iguales (50/50 al iniciar).

Archivos que genera:

- `v2/live_state_multi.json` (estado actual y equity por símbolo)
- `v2/live_trades_multi.jsonl` (eventos OPEN/CLOSE)

Para probar un solo ciclo y salir:

```bash
python -m v2.live_runner --symbol BTCUSDT --interval 15m --equity 100 --once
```

## Proximo paso

Si el backtest base no supera profit factor > 1.2 y DD acotado, no se escala.

## Docker (runner continuo + frontend)

Desde la raiz del repo:

```bash
docker compose -f docker-compose.v2.yml up -d --build
```

Si el puerto `3003` ya esta ocupado, podes elegir otro:

```bash
V2_FRONT_PORT=3003 docker compose -f docker-compose.v2.yml up -d --build
```

Esto levanta:

- `tincho-v2-runner` (paper runner continuo)
- `tincho-v2-frontend` (monitor en `http://localhost:3003/v2`)

Para ver logs:

```bash
docker compose -f docker-compose.v2.yml logs -f v2-runner
```

Para detener:

```bash
docker compose -f docker-compose.v2.yml down
```

### Launcher con doble click (Windows)

- `start_v2_docker.bat`: levanta Docker y abre el navegador en `/v2`
- `stop_v2_docker.bat`: detiene los contenedores v2

### Aprendizaje adaptativo v2

`v2.live_runner` ahora ajusta en runtime y persiste:

- `risk_per_trade`
- `stop_loss_pct`
- `take_profit_pct`
- `long_rsi_min`
- `short_rsi_max`

Archivo generado:

- `v2/adaptive_state.json` (o la ruta definida con `--adaptive-file`)
