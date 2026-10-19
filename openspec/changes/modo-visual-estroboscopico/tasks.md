# Tasks

## 1. Núcleo de capacidad visual (`visual.py`)

- [x] 1.1 Crear `visual.py` con función pura `visual_capability(rate_hz, refresh_hz)` que devuelva estado (`exacto`, `aproximado`, `armonico`, `no_disponible`), fotogramas por período, frecuencia efectiva y jitter esperado. Verificar con `tests/test_visual_capability.py`: pantalla 59.8 → 29.9 exacto, 10 exacto, 16 aproximado, 40 no disponible; pantalla 120 → 40 exacto (3 fotogramas). ✔ tests `TestVisualCapabilityTable` en verde.
- [x] 1.2 Implementar la generación de patrones: exacto (duty 50%), aproximado (ventana periódica de fotogramas ≤1 s) y armónico (3 fotogramas, duty 1/3). Verificar en tests que período y duty son correctos y que la relación de coeficientes del armónico es ≈0.5. ✔ `TestPatterns` (duty 50% en n par, ventana ≤1 s, patrón armónico `[1,0,0]` y `harmonic_amplitude_ratio` ≈ 0.5).
- [x] 1.3 Cubrir en tests el gate de rampa (peor punto del barrido) y el rechazo de emisión cruda (`f > refresh/2` no entrega `exacto` ni `aproximado`); `python run_tests.py` en verde. ✔ `TestRampGate` + `TestRawEmissionRejection`; suite completa: 133 tests en verde (headless).

## 2. Calibración y persistencia

- [x] 2.1 Implementar la medición de refresh (ventana fullscreen ~2 s, `perf_counter` por presentación, mediana + jitter p95). Verificar con test que inyecta un reloj falso y comprueba las estadísticas. ✔ `compute_refresh_stats` pura + `TestRefreshStats` (marcas sintéticas a 59.8 Hz, jitter medido, validación de plausibilidad); el bucle Tk vive en `run_screen_calibration()`.
- [x] 2.2 Persistir calibración (`refresh_hz`, `jitter_ms`, fecha) y preferencias (consentimiento, intensidad, flag armónico) en `~/.neuralbeat/config.json`. Verificar: test de compatibilidad (config sin claves nuevas no rompe) e inspección del archivo tras calibrar. ✔ `TestVisualConfig` (sección ausente/parcial/inválida → defaults); `run_screen_calibration()` escribe `refresh_hz`, `jitter_ms`, `calibrated_at`, `confidence`.
- [x] 2.3 Añadir "Recalibrar pantalla" al menú Settings. Verificar ejecutando la acción y viendo el valor actualizado en `config.json` (y que el estado del botón se recalcula). ✔ Implementado en Settings → Visual → Recalibrar pantalla: persiste y llama a `update_visual_button()`; la ejecución en pantalla real queda recogida en 7.1.

## 3. Ventana fullscreen y sincronía

- [x] 3.1 Crear la ventana fullscreen (Toplevel + canvas) que alterna color según la pareja de intensidad. Verificar manualmente que ocupa la pantalla y que cualquier tecla, clic, o `Escape` la cierra restaurando el foco. ✔ Implementada en `start_visual_mode()` (binds `<Key>`, `<Button-1..3>`, `WM_DELETE`; `root.focus_set()` al cerrar); verificación en pantalla recogida en 7.1.
- [x] 3.2 Implementar el scheduler de deadlines absolutos anclado a `samples_generated` del audio con re-anclaje cada ~1 s. Verificar con test de reloj falso (no acumula atraso; los flips tardíos se saltan) y manualmente contra el pulso isocrónico audible. ✔ `StrobeScheduler` + `TestStrobeScheduler`: ritmo/fase exactos, salto sin ráfada al llegar tarde, re-anclaje que absorbe deriva del 0.5 % del cristal, parada al congelarse el audio, rebuild de patrón en rampas; chequeo audible en 7.1.
- [x] 3.3 Cerrar el modo cuando el audio se detiene o termina. Verificar manualmente: pulsar Stop y dejar terminar una rampa → la ventana se cierra sola. ✔ `stop_audio()` cierra el modo y `visual_poll()` vigila `is_playing`, identidad del generador e `is_finished` (fin natural con fade-out); comprobación en pantalla en 7.1.

## 4. UI: botón, estados, sustituto y armónico

- [x] 4.1 Botón "Modo visual" con estado visible (exacto/aproximado/armónico/no disponible + razón) que se actualiza al cambiar ritmo, categoría o barrido de rampa. Verificar: en 59.8 el preset de 40 Hz aparece bloqueado con razón; 10 Hz aparece exacto. ✔ Botón + etiqueta de estado con razón y feedback de potencia; se recalcula con traces de `beat_type_var`/`ramp_enabled_var`, `<KeyRelease>` de entradas, `apply_preset()` y `play_audio()`; resolución del ritmo cubrida por `TestRateRequest` (40 Hz → `no_disponible` en 59.8 por construcción del gate).
- [x] 4.2 Ofrecer el sustituto al máximo real ("usar 29.9 Hz") a un clic cuando el ritmo no está disponible, etiquetado como frecuencia distinta a la pedida. ✔ `best_substitute()` + diálogo en `toggle_visual_mode()` con etiqueta "(sustituto: frecuencia distinta a la pedida)"; unit-tests `TestHarmonicAndSubstitute`.
- [x] 4.3 Modo armónico opt-in (flag avanzado, apagado por defecto) con etiqueta experimental y aviso de la componente adicional ~19.9 Hz. Verificar: sin flag no aparece; con flag, 40 Hz en 59.8 usa período de 3 fotogramas y etiqueta "≈39.87 Hz por armónico". ✔ `harmonics_enabled` en config (default False) + checkbutton en Settings → Visual; `TestHarmonicAndSubstitute` cubre ambos casos.
- [x] 4.4 Feedback de potencia: etiquetas por estado (jitter en milisegundos en aproximados, menor potencia en armónico, nota en intensidad cómoda). Verificar con tests unitarios de la lógica de etiquetas y comprobación visual en la app. ✔ `capability_label()` + `intensity_note()` con `TestLabels`; parte visual en 7.1.

## 5. Seguridad e intensidad

- [x] 5.1 Aviso de fotosensibilidad con aceptación explícita persistente la primera vez. Verificar: borrar la clave en `config.json` → reaparece el aviso; sin aceptar, el modo no arranca. ✔ `PHOTOSENSITIVE_WARNING` + consentimiento persistido en `config["visual"]["photosensitive_consent"]`; `toggle_visual_mode()` no arranca sin aceptación y el aviso reaparece si la clave no existe (`merge_visual_config` la trata como falsa).
- [x] 5.2 Intensidad cómoda por defecto y brillante opt-in con advertencia de contraste. Verificar: config nuevo → cómoda; al elegir brillante aparece la advertencia y el parpadeo usa máximo contraste. ✔ default `comoda`; radiobuttons en Settings → Visual con `showwarning` al elegir brillante; pares de color en `visual.INTENSITY_PAIRS`.
- [x] 5.3 Declaración visible de "no es dispositivo médico ni tratamiento" y ausencia de autoarranque al iniciar audio. Verificar manualmente leyendo la UI del modo visual y arrancando audio sin tocar el botón. ✔ Etiqueta fija en la barra del modo visual, en el aviso de consentimiento y en la etiqueta activa; `play_audio()` no toca el modo (solo actualiza su estado).

## 6. Documentación

- [x] 6.1 Documentar en `README.md` y `LEEME.md`: uso del modo visual, estados del gate, aviso PSE (incluida la advertencia del preset de 16 Hz por caer en la banda 15–25 Hz) y cómo desbloquear 40 Hz real (monitor ≥120 Hz o hardware externo). Verificar: seguir las instrucciones del doc reproduce el flujo real sin pasos faltantes. ✔ Secciones "Visual Strobe Mode" (README) y "Modo visual estroboscópico" (LEEME) + avisos en Disclaimer/FAQ.

## 7. Verificación de integración

- [ ] 7.1 En el hardware del autor (59.8 Hz): medir tasa lograda y jitter con audio sonando, comprobar salida con cualquier tecla, cierre al parar el audio, bloqueo de 40 Hz y que `python SourceCode.py --debug` sigue en verde (sin regresión del motor de audio). Registrar resultados en una nota de verificación dentro del change. ⏳ Pendiente de ejecución en el hardware del autor: ver `verification.md` (la parte automatizada ya está en verde: 133 tests, reporte DSP PASS, `verify_dsp_ramp.py` exit 0).

## 8. Correcciones tras las pruebas del autor (2026-10-19)

- [x] 8.1 El modo visual se cerraba ~1 ms después de abrirse: `start_visual_mode()` nunca llamaba a `scheduler.start()`, así `poll()` devolvía `None` y `visual_poll()` lo interpretaba como "el audio no avanza" (afectaba a todos los ritmos; 40 Hz solo *parecía* funcionar porque su diálogo de gate queda visible). ✔ `scheduler.start()` antes del primer poll + `TestVisualModeStart`; en pantalla real se mantuvo >1.8 s con isocrónico 16 Hz y cerró con `Escape`.
- [x] 8.2 Botón "Modo visual" y su etiqueta de estado quedaban recortados y, al ensanchar el texto la ventana, la columna de presets isocrónicos se salía de pantalla. ✔ Botón, estado y aviso movidos a la barra inferior con `wraplength`; ventana 1308×714 con todos los controles visibles.
- [x] 8.3 Si la calibración no es plausible, usar el refresco nominal de `xrandr --current` (`confidence: "sistema"`, valor no medido) en lugar del default de 60 Hz. ✔ `parse_xrandr_refresh_hz()` + `probe_system_refresh_hz()` con `TestSystemRefreshProbe`; la ejecución de "Recalibrar pantalla" en el panel real queda para 7.1.
- [x] 8.4 Suite completa tras los cambios: 137 tests en verde.

## Workflow follow-up

- Archivar el change cuando la revisión esté satisfecha (`openspec archive modo-visual-estroboscopico`).
- Verificar que `openspec/specs/estimulacion-visual/spec.md` existe con las requirements archivadas.
