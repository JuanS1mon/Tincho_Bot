# GIFs del Dashboard

Colocá tus GIFs animados en esta carpeta con los siguientes nombres exactos:

| Archivo | Cuándo se muestra |
|---|---|
| `no-trading.gif` | Cuando NO hay señal de trading (todos los pares sin señal) |
| `trading.gif` | Cuando hay posiciones activas abiertas |

## Ejemplo de uso

```
frontend/public/no-trading.gif   ← tu GIF de "sin operaciones"
frontend/public/trading.gif      ← tu GIF de "operando activamente"
```

Los archivos en `/public` son servidos directamente por Next.js como `/no-trading.gif` y `/trading.gif`.

Puede ser cualquier formato: `.gif`, `.webp`, `.mp4` (cambiar el `src` en page.tsx en ese caso).
