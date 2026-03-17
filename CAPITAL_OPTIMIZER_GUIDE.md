# CAPITAL OPTIMIZER - Reallocación Dinámica de Capital

## 🎯 Descripción

El **Capital Optimizer** es un sistema que Tincho1 usa para detectar cuándo hay posiciones abiertas con rendimientos muy diferentes y **automáticamente reallocar el capital** hacia la más rentable.

### Ejemplo Real:
```
Ciclo #47 - Análisis de posiciones:
├─ ETHUSDT: PnL = +1.0% (20 USDT invertido)
├─ BTCUSDT: PnL = +5.0% (30 USDT invertido)
└─ Divergencia: 4.0% → ⚠️  REALLOCATE!

Acción:
✅ Cierra ETHUSDT con ganancia de 0.20 USDT
🔄 Reinvierte 20 USDT en BTCUSDT
📊 Resultado: 100% capital en activo más rentable
```

---

## ⚙️ Configuración

### Variables de Entorno (.env)

Agrega estas líneas a tu `.env`:

```env
# ============================================================
# CAPITAL OPTIMIZER (reallocación dinámica)
# ============================================================
CAPITAL_REALLOCATION_ENABLED=True
CAPITAL_REALLOCATION_MIN_DIVERGENCE_PCT=4.0
CAPITAL_REALLOCATION_CHECK_INTERVAL_CYCLES=5
CAPITAL_REALLOCATION_MIN_AMOUNT=10.0
```

### Explicación de Parámetros

| Parámetro | Valor | Rango | Descripción |
|-----------|-------|-------|-------------|
| `CAPITAL_REALLOCATION_ENABLED` | `True` | bool | Activa/desactiva el optimizer completamente |
| `CAPITAL_REALLOCATION_MIN_DIVERGENCE_PCT` | `4.0` | 0.5-20.0 | Diferencia mínima de PnL% para reallocar (ej: 4% = si BTC da +5% y ETH da +1%) |
| `CAPITAL_REALLOCATION_CHECK_INTERVAL_CYCLES` | `5` | 1-20 | Cada cuántos ciclos revisar si hay que reallocar (no en cada ciclo para ahorrar CPU) |
| `CAPITAL_REALLOCATION_MIN_AMOUNT` | `10.0` | 5.0-100.0 | Capital mínimo en USDT para que valga la pena cerrar una posición |

---

## 🔄 Cómo Funciona

### 1. **Detección de Rendimientos**
Cada X ciclos (configurable), Tincho1 analiza TODAS las posiciones abiertas y calcula su PnL%:

```python
posiciones_abiertas = {
    "BTCUSDT": Position(unrealized_pnl_pct=+5.2%),
    "ETHUSDT": Position(unrealized_pnl_pct=+1.1%),
    "XAUUSDT": Position(unrealized_pnl_pct=-0.5%),
}
```

### 2. **Cálculo de Divergencia**
```
mejor_pnl = max([+5.2%, +1.1%, -0.5%]) = +5.2% (BTC)
peor_pnl = min([+5.2%, +1.1%, -0.5%]) = -0.5% (XAU)
divergencia = 5.2% - (-0.5%) = 5.7%

¿5.7% > 4.0% (umbral)? → SÍ → REALLOCAR
```

### 3. **Ejecución de Reallocación**
Si la divergencia supera el umbral:

✅ **Cierra la posición peor** (aquella con pnl_pct más bajo)
🔄 **Reinvierte el capital** en la posición mejor
📝 **Registra la transacción** como trade con estrategia `CAPITAL_REALLOC`

---

## 📊 Monitoreo y Logs

### Logs en Consola

```
[TRADING] 📊 [CapOptimizer] Análisis: BTCUSDT (+5.2%) vs ETHUSDT (+1.1%) | Divergencia: 4.1%
[TRADING] ⚠️  [CapOptimizer] REALLOC recomendada: Cerrar ETHUSDT (+1.1%, 20 USDT) y reinvertir en BTCUSDT (+5.2%)
[TRADING] 💰 [REALLOCATION] Cerrando ETHUSDT (20 USDT) para reinvertir en BTCUSDT
[TRADING] 🔄 REALLOC ETHUSDT | entrada=1930 | salida=1950 | PnL=+0.20 USDT (+1.0%)
```

### Estado en API

Cuando Tincho1 realiza una reallocación, puedes verlo en:
- Dashboard: "Log de Ciclos" mostrará `💰 Capital reallocado: ETHUSDT → BTCUSDT`
- API `/portfolio`: El trade aparecerá con `strategy: "CAPITAL_REALLOC"`
- MongoDB: El trade se guarda en la colección `trades`

---

## 🎮 Ejemplos de Uso

### Ejemplo 1: Configuración Conservadora
Para trading con capital pequeño (<100 USDT), aumenta el umbral:

```env
CAPITAL_REALLOCATION_ENABLED=True
CAPITAL_REALLOCATION_MIN_DIVERGENCE_PCT=6.0  # Solo reallocar si hay >6% diferencia
CAPITAL_REALLOCATION_CHECK_INTERVAL_CYCLES=10  # Revisar menos frecuentemente
CAPITAL_REALLOCATION_MIN_AMOUNT=15.0  # Solo si hay >15 USDT para mover
```

### Ejemplo 2: Configuración Agresiva
Para trading con capital grande (>500 USDT), baja el umbral:

```env
CAPITAL_REALLOCATION_ENABLED=True
CAPITAL_REALLOCATION_MIN_DIVERGENCE_PCT=2.0  # Reallocar con cualquier divergencia
CAPITAL_REALLOCATION_CHECK_INTERVAL_CYCLES=3  # Revisar frecuentemente
CAPITAL_REALLOCATION_MIN_AMOUNT=5.0  # Reallocar incluso montos pequeños
```

### Ejemplo 3: Desactivado
Si no quieres usar el optimizer:

```env
CAPITAL_REALLOCATION_ENABLED=False
```

---

## ⚠️ Consideraciones

### Pro (Ventajas)
✅ **Maximiza rentabilidad** enfocando capital en activos de mejor rendimiento  
✅ **Adaptativo** - se ajusta automáticamente según el mercado  
✅ **Sin intervención** - funciona 24/7 sin que hagas nada  
✅ **Configurable** - adapta los umbrales a tu estrategia  

### Contra (Desventajas)
⚠️ **Costos de realización** - cada cierre genera fee de Binance (~0.04% maker)  
⚠️ **Timing imperfecto** - puede cerrar ETH justo cuando estaba a punto de subir  
⚠️ **Datos históricos** - solo mira PnL actual, no tendencias futuras  

---

## 🔧 Troubleshooting

| Problema | Causa | Solución |
|----------|-------|----------|
| El optimizer nunca se activa | `CAPITAL_REALLOCATION_ENABLED=False` | Cambia a `True` en .env |
| Se reallocan posiciones constantemente | Umbral muy bajo | Aumenta `MIN_DIVERGENCE_PCT` a 5-6% |
| Nunca se reallocan | Umbral muy alto | Baja `MIN_DIVERGENCE_PCT` a 2-3% |
| Se reallocan posiciones pequeñas | `MIN_AMOUNT` muy bajo | Aumenta a 15-20 USDT |

---

## 📈 Estadísticas y Análisis

El Capital Optimizer también proporciona estadísticas de rendimiento que puedes consultar:

```python
from tools.capital_optimizer_tool import capital_optimizer
from tools.portfolio_tool import portfolio_tool

# Obtener estadísticas
stats = capital_optimizer.get_statistics(portfolio_tool.positions)

print(f"Posiciones: {stats['total_positions']}")
print(f"Mejor: {stats['best_symbol']} ({stats['best_pnl_pct']:.2f}%)")
print(f"Peor: {stats['worst_symbol']} ({stats['worst_pnl_pct']:.2f}%)")
print(f"Divergencia: {stats['divergence']:.2f}%")
```

---

## 🚀 Próximas Mejoras

- [ ] Snap de realallocation a múltiples posiciones (ej: cerrar 3 malas, reinvertir en 1 buena)
- [ ] Predicción de tendencias antes de reallocar
- [ ] Análisis de volatilidad histórica
- [ ] Configuración adaptativa basada en win_rate
- [ ] Dashboard en tiempo real de PnL divergencia

---

**Última actualización**: Marzo 2025  
**Estado**: ✅ Funcional y testeado
