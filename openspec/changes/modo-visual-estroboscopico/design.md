# Design

## Context

Ver `proposal.md` para motivación. Estado actual relevante:

- App Tkinter/ttkbootstrap (`SourceCode.py`) + módulos planos (`presets.py`, `verification.py`); tests con `unittest`/`pytest` en `tests/`.
- Motor de audio: `sounddevice` callback por bloques con fase sample-exacta y contador `samples_generated` que es la referencia de tiempo del audio (ver `AudioEngine`/`BinauralGenerator`).
- Pantalla del autor: 1366×768 LVDS @ 59.80 Hz reales, sesión Wayland/KDE (XWayland para Tk).
- Restricción física: la luz solo cambia en fronteras de fotograma → máximo fundamental = refresh/2; emitir 40 Hz crudo en 59.8 Hz produce una réplica dominante en ~19.8 Hz (alias), no 40 Hz.

## Goals / Non-Goals

**Goals:**
- Sincronía audio-visual con el pulso real del audio (ritmo y fase), sin tocar el camino crítico del audio.
- Capacidad de pantalla medida y recomputada en runtime: mejor hardware ⇒ mejor soporte sin cambios de código.
- Gate honesto con estados visibles y feedback de potencia; alternativas etiquetadas.
- Cero dependencias nuevas; cero riesgo de glitch para el motor de audio existente.

**Non-Goals:**
- 40 Hz real por hardware externo (gafas LED, monitor 120 Hz+): solo documentado.
- Emisión cruda sin gate (descartada por alias). Perfiles multi-monitor simultáneos.
- Cualquier afirmación terapéutica o de dispositivo médico.

## Decisions

1. **Capacidad desde medición propia, no valor fijo ni `xrandr`.**
   Calibración: ventana a pantalla completa ~2 s alternando y cronometrando cada presentación con `time.perf_counter()`; se guardan `refresh_hz` (mediana) y `jitter_ms` (p95 del desvío) en `~/.neuralbeat/config.json`.
   Alternativas: hardcodear 60 (rompe "monitor mejor ⇒ funciona mejor"); `xrandr`/`kscreen-doctor` (solo X11 o específico de escritorio, no mide jitter real del pipeline Tk+compositor). La medición cubre Wayland, XWayland y monitores externos sin cambios.

2. **Clasificación de ritmos (regla de gate).** Con refresh medido `R` y ritmo pedido `f`:
   - `f > R/2` → **no disponible** (no existe fundamental presentable).
   - `R/f` entero → **exacto** (duty 50%, patrón fijo de fotogramas).
   - resto → **aproximado** con patrón periódico de fotogramas (ventana de repetición ≤ ~1 s); se reporta jitter esperado.
   - armónico (opt-in) → patrón de 3 fotogramas a `R/3` (19.93 Hz en 59.8) con duty 1/3: `|c2|/|c1| = 0.5`, 2º armónico en ≈39.87 Hz; etiquetado experimental.
   Ejemplos calculados: 59.8 Hz → exactos 29.9 (2f), 19.93 (3f), 14.95 (4f), 11.96 (5f), 9.97 (6f); 120 Hz → 40 Hz exacto (3f).

3. **Reloj maestro = audio.** La programación visual se ancla a `samples_generated / sample_rate`, con re-anclaje periódico (cada ~1 s) a `perf_counter()` para absorber la diferencia entre el cristal de la tarjeta (~10–100 ppm) y el reloj del sistema. El primer pulso visual se alinea a una frontera de pulso de audio. Alternativas: `monotonic` puro (deriva acumulada de hasta medio ciclo en sesiones de 10 min); alinear solo al inicio (suficiente a corto plazo, se degrada).

4. **Scheduler por deadlines absolutos en el hilo Tk (`after`).** Cada flip se agenda a `t0 + k·T`; si llega tarde se salta al siguiente k (no acumula atraso). Se acepta y declara el jitter de ms del pipeline Tk+KWin; no se persigue la precisión de µs del audio (imposible sin control de vsync). Alternativa descartada: bucle ocupado con `update_idletasks()` (quema CPU y sigue limitado por el compositor).

5. **`visual.py` como módulo nuevo; `SourceCode.py` solo gana botón, estados y bindings.** El scheduler solo *lee* del motor (`samples_generated`, `is_playing`); no escribe ni bloquea el callback de audio. Rollback trivial: quitar botón/módulo.

6. **Alternativas de pantalla descartadas (registro).** Emisión cruda 40 Hz (O3): réplicas ZOH → sinc(19.8/R)≈0.89 vs sinc(40/R)≈0.47 ⇒ componente dominante ~19.8 Hz, banda equivocada y en la ventana de máximo riesgo PSE. Black-frame insertion y trucos tipo FPS: cambian cuándo se presenta un fotograma, no crean resolución temporal entre fotogramas (pared de Nyquist). Escalado a hardware externo: fuera de alcance, documentado.

7. **Seguridad fotosensible como requisito de producto.** Consentimiento persistente la primera vez; default intensidad cómoda (nota de menor potencia); jamás autoarranque; salida por cualquier tecla/clic; abort automático si la tasa lograda durante la sesión cae bajo la requerida (p. ej. mediana >15% fuera). El preset existente de 16 Hz es advertido explícitamente en docs por caer en la banda 15–25 Hz de máximo riesgo.

8. **Modo armónico detrás de opción avanzada** (`config["visual"]["harmonics_enabled"]`), apagado por defecto; se ofrece como acción explícita cuando el ritmo pedido está no disponible y existe patrón armónico candidato.

## Risks / Trade-offs

- [PSE] → consentimiento + default cómodo + no autoarranque + kill switch en cualquier tecla; 16 Hz advertido en docs. No elimina el riesgo por completo: inherente al estrobo.
- [Jitter del compositor] → deadlines absolutos + medición real + etiqueta "aproximado" + abort automático; nunca se promete precisión de µs.
- [Panel lento (LVDS)] → el contraste útil siempre será menor que en un panel moderno; se ofrece intensidad brillante y nota de potencia. No se promete ganancia cuantificada.
- [Deriva del cristal de audio] → re-anclaje periódico (~1 s).
- [Calibración bajo carga] → se publican jitter y confianza; recalibrar a demanda; gate conservador (si la medición es inestable, se clasifica peor).
- [Texto terapéutico] → declaración "no es dispositivo médico" en UI y docs.

## Migration Plan

Sin migración de datos: las claves nuevas de config son opcionales y compatibles hacia atrás; versiones anteriores las ignoran. Rollback = eliminar botón + módulo (la app queda idéntica a hoy).

## Open Questions

- Detección automática de hotplug/cambio de pantalla: diferido; la recalibración manual lo cubre en v1.
