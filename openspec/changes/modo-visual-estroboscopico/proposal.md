# Proposal

## Why

NeuralBeat genera audio sample-exacto (fases continuas, fades de 20 ms, sin glitches), pero no ofrece apoyo visual. La evidencia EEG (SSVEP / fotoconducción) y el protocolo 40 Hz luz+sonido (Cognito/GENUS, ensayo pivotal HOPE) usan luz y sonido al mismo ritmo: un modo visual sincronizado convierte el motor actual en estimulación audiovisual real.

Restricción dura descubierta durante la exploración: un panel de 59.8 Hz solo puede producir flicker con fundamental ≤ 29.9 Hz (Nyquist + rejilla de frames). Emitir 40 Hz "a la brava" no da 40 Hz: el muestreo alíasea a un componente dominante de ~19.8 Hz (banda equivocada y dentro de la zona de máximo riesgo de epilepsia fotosensible). Por tanto el producto necesita un gate honesto, feedback de potencia y alternativas etiquetadas — nunca un botón que prometa lo que la pantalla no puede entregar.

## What Changes

- Nuevo botón "Modo visual" que abre un estroboscopio a **pantalla completa solo mientras suena audio**, con ritmo y fase tomados del pulso de audio (binaural: `|right−left|`; isocrónico: `pulse_hz`; rampa: peor punto del barrido).
- **Calibración en runtime**: el refresco real de la pantalla se mide (flips cronometrados) y la capacidad se calcula en el momento: exacto / aproximado / armónico experimental / no disponible. Sin valores hardcodeados: al usar un monitor mejor (p. ej. 120 Hz) la capacidad mejora automáticamente y 40 Hz se desbloquea solo, sin cambios de código.
- **Estados visibles y feedback de potencia** en el botón/UI: razón cuando está bloqueado, jitter cuando es aproximado, aviso de potencia reducida cuando aplica (armónico, intensidad cómoda, interpolación). Nunca arranca en silencio un ritmo no soportado.
- **Sustituto a un click** cuando el ritmo pedido excede el máximo real: "usar el máximo de tu pantalla" (29.9 Hz en 59.8), etiquetado como frecuencia distinta a la del protocolo 40 Hz.
- **Modo armónico experimental (opt-in, avanzado)**: pulso de 19.93 Hz (1 frame on / 2 off, período entero, cero jitter) cuyo 2º armónico cae en ≈ 39.87 Hz; etiquetado como experimental (potencia menor que la fundamental y añade componente 19.9 Hz).
- **Salida inmediata**: cualquier tecla, click, o parada/fin del audio cierra el modo y restaura la ventana.
- **Seguridad fotosensible**: aviso de epilepsia + aceptación explícita la primera vez, intensidad "cómoda" por defecto (con nota de menor potencia), nunca auto-arranque.
- Descartado explícitamente: emisión cruda de 40 Hz en pantallas de 60 Hz (alias dominante ~19.8 Hz) y estroboscopios de hardware externo o teléfono (fuera de alcance v1; documentado en README como la vía al 40 Hz real).

## Capabilities

### New Capabilities

- `estimulacion-visual`: modo visual estroboscópico acoplado al motor de audio; capacidad de pantalla medida en runtime; gate y estados de soporte con feedback de potencia; alternativas etiquetadas (sustituto al máximo real y armónico experimental); salida inmediata; salvaguardas fotosensibles; intensidad configurable.

### Modified Capabilities

Ninguna (el proyecto no tiene specs todavía).

## Impact

- Código: `SourceCode.py` (botón, bindings, ventana fullscreen, gancho con el motor), nuevo módulo `visual.py` (calibración, cálculo de capacidad, patrones de frames, scheduler sincronizado).
- Configuración: `~/.neuralbeat/config.json` gana calibración de pantalla, consentimiento fotosensible e intensidad elegida.
- Tests: `tests/test_visual_capability.py` (tabla de capacidad por refresco, patrones exactos/armónicos, gate sobre rampa).
- Docs: `README.md` y `LEEME.md` (uso del modo visual, aviso fotosensible, cómo desbloquear 40 Hz real con hardware adecuado).
- Sin dependencias nuevas (tkinter, numpy y sounddevice ya están).
