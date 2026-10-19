# Nota de verificación — modo-visual-estroboscopico

Fecha: 2026-10-19 · Entorno de aplicación: sandbox Linux headless (Python 3.12,
numpy 2.2.4 real, scipy/sounddevice/ttkbootstrap/matplotlib instalados;
interfaz gráfica vía Xvfb 1366×768 solo para tkinter puro).

## Verificación automatizada (en verde)

- `python run_tests.py` → **133 passed, 0 failed** (también sin `DISPLAY`).
  Incluye los 49 tests nuevos de `tests/test_visual_capability.py`:
  - Tabla de capacidad: 59.8 Hz → 29.9 exacto / 10 exacto (@9.97) / 16
    aproximado (jitter ≈ 16.7 ms, ventana 15 frames = 0.25 s) / 40 no
    disponible; 120 Hz → 40 exacto (3 fotogramas).
  - Rechazo de emisión cruda: f > R/2 (30.5–100 Hz en 59.8) nunca entrega
    `exacto` ni `aproximado`.
  - Patrones: duty 50% exacto en períodos pares; armónico `[1,0,0]` con
    |c2|/|c1| = 0.5 (duty 1/3); sustituto = R/2 exacto.
  - Gate de rampa por peor punto: 3→40 y 40→3 bloquean; 20→3 da aproximado.
  - Scheduler con reloj falso: flips en la frontera del pulso de audio
    (±1.5 ms), duty ~50%, salto único sin ráfaga al llegar tarde (~15 flips
    perdidos → 1 flip al estado correcto), re-anclaje cada 1 s que mantiene la
    fase enganchada con un audio 0.5% más rápido (error < 6.5 ms), congelado
    del audio → sin flips, rebuild de patrón en re-anclaje (rampas).
  - Estadísticas de calibración: mediana ≈ 59.8 Hz con 120 marcas limpias;
    jitter p95 medido con ruido; validación de plausibilidad.
  - Compatibilidad de config: sección `visual` ausente/parcial/inválida →
    defaults (consentimiento falso, intensidad cómoda, armónico off).
- Réplica del bloque `--debug` (motor DSP sin GUI): **Signal Verification
  PASS · Export Verification PASS** (427/437 Hz, 1 s, sin regresión).
- `python tests/verify_dsp_ramp.py` → exit 0.

## Reparaciones colaterales en la suite (preexistentes, sin relación con el DSP)

La suite no llegaba a ejecutarse en este entorno (la colección de pytest se
interrumpía). Causas latentes corregidas:

- `tests/conftest.py` (nuevo): pre-instala una sola vez los mocks de
  tkinter/matplotlib/sounddevice/ttkbootstrap y las constantes de Tk
  (`END='end'`, `TclError`), haciendo el orden de importación determinista.
- `test_audio_engine.py` / `test_config.py`: sus `@patch('SourceCode.sd', mock)`
  con `new` explícito no inyectaban el argumento esperado (y compartían un
  único mock entre tests). Ahora inyectan mocks frescos; `test_stop` captura el
  stream antes de que `stop()` lo anule; `test_save_config` parchea también
  `APP_DIR` (que es quien recibe `mkdir`).
- `test_ui_logic.py`: el decorador `patch_ui_globals` usaba `new` explícito y
  por eso no inyectaba los 14 mocks que los tests desempaquetan.
- `test_dsp_generators.py`: instalaba mocks en `sys.modules` sin guarda (des-
  sincronizaba `SourceCode.tk`); `test_fade_out` esperaba 512 muestras en
  silencio cuando el fade de 20 ms son 882; `test_noise_mixing` comparaba RMS
  con volumen 0.8, donde el limitador suave invierte la orden (verificado
  numéricamente: 0.5205 < 0.5282); con volumen 0.3 la orden es robusta.
- `test_generators.py`: referenciaba `MonauralGenerator`, clase inexistente
  (los tonos monaurales van por `BinauralGenerator` con canales iguales).
- `SourceCode.py`: declarados a nivel de módulo los widgets de UI que los
  tests parchean (mismo patrón que `beat_type_var`); sin esto, `patch()`
  fallaba con AttributeError antes de que `main()` existiera.

## Correcciones tras las pruebas en el escritorio real (2026-10-19)

Sesión sobre el panel 1366×768 @ 59.8 Hz (KDE Wayland / XWayland), app lanzada
desde el fork, con isocrónico 16 Hz y volúmenes a 0 para no emitir sonido:

- `start_visual_mode()` ya arranca el scheduler: el modo abrió a pantalla
  completa, sobrevivió más de 1.8 s (antes se cerraba en ~1 ms) y cerró con
  `Escape`, sin traza en stderr. Capturas durante el modo: fotogramas
  uniformes 201,201,201 = estado claro de la intensidad cómoda.
- Layout: ventana 1308×714; botón "Modo visual — aproximado" (ámbar en 16 Hz),
  etiqueta de estado ("Visual: Aproximado @ 16.00 Hz · jitter ±17 ms …") y
  columna de presets isocrónicos completos, sin recortes.
- Fallback de refresco (8.3): cubierto por unit tests (`parse_xrandr_refresh_hz`
  con salidas reales de `xrandr --current`); la ejecución de
  "Recalibrar pantalla" sobre este panel queda para 7.1.
- `venv/bin/python run_tests.py` → **137 passed, 0 failed**.

## Pendiente en el hardware del autor (task 7.1)

En este sandbox no es posible ejercitar la GUI (el `_tkagg` del matplotlib del
venv enlaza contra Tcl 8.6 mientras el intérprete uv trae Tcl 9: `ImportError:
Failed to load Tcl_SetVar`; tk puro sí funciona sobre Xvfb). Queda por medir
en el panel de 59.8 Hz real:

1. Calibrar (Settings → Visual → Recalibrar pantalla) y confirmar
   `~/.neuralbeat/config.json` (`refresh_hz` ≈ 59.8, `jitter_ms`, fecha).
2. Con audio sonando (p. ej. 10 Hz): tasa lograda y jitter con audio activo.
3. Salida con cualquier tecla y con clic; cierre automático al pulsar Stop y
   al terminar una rampa.
4. Bloqueo del preset de 40 Hz con la razón visible; sustituto "usar 29.9 Hz"
   etiquetado como frecuencia distinta; armónico ≈39.87 Hz solo con el flag.
5. `python SourceCode.py --debug` en verde en la máquina del autor.

El abort automático por tasa insuficiente (mediana de lateness > 15% del
fotograma durante ≥2 s) queda activo por defecto durante las sesiones.
