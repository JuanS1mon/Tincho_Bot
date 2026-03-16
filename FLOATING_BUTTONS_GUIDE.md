# Guía de Botones Flotantes Movibles (Draggeable Floating Buttons)

## 📍 Descripción General

Los 4 botones flotantes principales del dashboard ya son **completamente movibles** (draggeable) y **se adhieren automáticamente al borde más cercano** (snap-to-edge).

## 🎯 Botones Implementados

| Ícono | Nombre | Función | Posición Inicial |
|-------|--------|---------|-----------------|
| 🤖 | Tincho2 | Chat con IA asesor de trading | Derecha abajo |
| ⚡ | Marquitos | Monitor de estado de Marquitos (bot alternativo) | Izquierda abajo |
| 🐂 | BULLISH | Compra manual de assets | Derecha abajo |
| 💣 | BOMBARDA | Cierre de todas las posiciones | Derecha abajo |

## ✨ Características

### 1. **Drag & Drop**
- Haz **clic y arrastra** cualquier botón para moverlo a donde quieras
- El cursor cambia a `grab` cuando pasas sobre un botón flotante
- Mientras arrastras, el cursor es `grabbing`

### 2. **Auto-Snap a Bordes**
- Cuando **sueltas** un botón a menos de **40px** del borde de la pantalla, se adhiere automáticamente
- Snapping funciona en todos los bordes: izquierda, derecha, arriba, abajo
- Los botones nunca se salen de la pantalla visible

### 3. **Persistencia en LocalStorage**
- Cada botón guarda su posición en `localStorage` 
- Las posiciones se **recuerdan entre sesiones** (incluso si recargas la página)
- Cada botón tiene su propia clave de almacenamiento:
  - `float_tincho2` → Posición del chat Tincho2
  - `float_bullish` → Posición del botón BULLISH
  - `float_bombarda` → Posición del botón BOMBARDA
  - `float_marquitos` → Posición del botón Marquitos

### 4. **Suavidad Visual**
- Las transiciones son suaves gracias a CSS `transition: all 0.2s ease-out`
- El snapping es automático y fluido
- Sin jalones ni saltos abruptos

## 🔧 Implementación Técnica

### Hook Custom: `useDraggableFloat`
Ubicación: `frontend/app/hooks/useDraggableFloat.ts`

```typescript
export function useDraggableFloat<T extends HTMLElement = HTMLDivElement>(
  storageKey: string,
  defaultPos: FloatPosition = DEFAULT_POS
)
```

#### Propiedades Devueltas:
```typescript
{
  position: FloatPosition          // { x: number, y: number }
  isDragging: boolean             // Si está siendo arrastrado actualmente
  elementRef: RefObject<T>         // Referencia al elemento HTML
  handleMouseDown: (e: React.MouseEvent) => void  // Handler de inicio del drag
  style: React.CSSProperties      // Estilos CSS para aplicar al elemento
}
```

### Integración en Componentes

#### Tincho2Chat (Button + Panel):
```typescript
const tincho2Float = useDraggableFloat<HTMLButtonElement>(
  "float_tincho2", 
  { x: windowWidth - 100, y: windowHeight - 200 }
);

// En el botón:
<button
  ref={tincho2Float.elementRef}
  onMouseDown={tincho2Float.handleMouseDown}
  style={tincho2Float.style}
  // ... resto de props
/>

// En el panel (se mueve con el botón):
<div style={{ 
  ...tincho2Float.style, 
  top: `${tincho2Float.position.y + 56}px`,
  left: `${tincho2Float.position.x - 352}px`
}}>
```

#### Botones BULLISH/BOMBARDA/Marquitos (Solo Button):
```typescript
const bullishFloat = useDraggableFloat<HTMLButtonElement>(
  "float_bullish",
  { x: windowWidth - 100, y: windowHeight - 200 }
);

<button
  ref={bullishFloat.elementRef}
  onMouseDown={bullishFloat.handleMouseDown}
  onClick={() => setShowBullish(true)}
  style={bullishFloat.style}
  // ... resto de props
/>
```

## 🎮 Cómo Usar

1. **Abrir Dashboard** → Ves los 4 botones flotantes
2. **Mover un botón** → Haz clic y arrastra
3. **Soltar botón** → Se adhiere automáticamente al borde más cercano
4. **Recarga la página** → Los botones mantienen su posición

## 📊 Beneficios

✅ **Máxima visibilidad** - Los iconos nunca tapan contenido importante
✅ **Personalizable** - Cada uno coloca sus botones donde más los necesita
✅ **Persistente** - Las preferencias se guardan automáticamente
✅ **Smooth UX** - Transiciones suaves, sin movimientos abruptos
✅ **Responsive** - Funciona en cualquier tamaño de pantalla

## 🚀 Commits Relacionados

- **3308afa** - Anterior: Conversion de botones a floating icons
- **[NUEVO]** - Refactor: Drag & drop con auto-snap a bordes

## 💡 Notas Técnicas

### localStorage Keys:
```javascript
{
  "float_tincho2": "{\"x\": 1280, \"y\": 600}",
  "float_bullish": "{\"x\": 1180, \"y\": 600}",
  "float_bombarda": "{\"x\": 1140, \"y\": 600}",
  "float_marquitos": "{\"x\": 20, \"y\": 600}"
}
```

### TypeScript Generics:
El hook usa genéricos para soportar cualquier tipo de elemento HTML:
- `useDraggableFloat<HTMLButtonElement>()` → Para botones
- `useDraggableFloat<HTMLDivElement>()` → Para divs/paneles

### Mouse Events:
- `onMouseDown` → Inicia el drag
- `document.mousemove` → Actualiza posición mientras se arrastra
- `document.mouseup` → Suelta y aplica snap automático

## 🐛 Troubleshooting

| Problema | Solución |
|----------|----------|
| Los botones no se guardan | Verifica que localStorage esté habilitado en el navegador |
| Comportamiento jerky | Recarga la página (raramente puede haber estado inconsistente) |
| Panel de Tincho2 no acompaña al botón | Verifica que el offset de posición sea correcto |

## 🔮 Mejoras Futuras (Posibles)

- [ ] Snap a grid (alineación de 10px)
- [ ] Botón "Reset to defaults" para restaurar posiciones originales
- [ ] Animación de bounce al soltar
- [ ] Soporte para touch/mobile events
- [ ] Atajos de teclado para posiciones presets

---

**Última actualización**: January 2025  
**Estado**: ✅ Funcional y testeado
