# Tasks

## 1. Núcleo de capacidad visual (`visual.py`)

- [ ] 1.1 Crear `visual.py` con función pura `visual_capability(rate_hz, refresh_hz)` que devuelva estado (`exacto`, `aproximado`, `armonico`, `no_disponible`), fotogramas por período, frecuencia efectiva y jitter esperado. Verificar con `tests/test_visual_capability.py`: pantalla 59.8 → 29.9 exacto, 10 exacto, 16 aproximado, 40 no disponible; pantalla 120 → 40 exacto (3 fotogramas).
- [ ] 1.2 Implementar la generación de patrones: exacto (duty 50%), aproximado (ventana periódica de fotogramas ≤1 s) y armónico (3 fotogramas, duty 1/3). Verificar en tests que período y duty son correctos y que la relación de coeficientes del armónico es ≈0.5.
- [ ] 1.3 Cubrir en tests el gate de rampa (peor punto del barrido) y el rechazo de emisión cruda (`f > refresh/2` no entrega `exacto` ni `aproximado`); `python run_tests.py` en verde.

## 2. Calibración y persistencia

- [ ] 2.1 Implementar la medición de refresh (ventana fullscreen ~2 s, `perf_counter` por presentación, mediana + jitter p95). Verificar con test que inyecta un reloj falso y comprueba las estadísticas.
- [ ] 2.2 Persistir calibración (`refresh_hz`, `jitter_ms`, fecha) y preferencias (consentimiento, intensidad, flag armónico) en `~/.neuralbeat/config.json`. Verificar: test de compatibilidad (config sin claves nuevas no rompe) e inspección del archivo tras calibrar.
- [ ] 2.3 Añadir "Recalibrar pantalla" al menú Settings. Verificar ejecutando la acción y viendo el valor actualizado en `config.json` (y que el estado del botón se recalcula).

## 3. Ventana fullscreen y sincronía

- [ ] 3.1 Crear la ventana fullscreen (Toplevel + canvas) que alterna color según la pareja de intensidad. Verificar manualmente que ocupa la pantalla y que cualquier tecla, clic, o `Escape` la cierra restaurando el foco.
- [ ] 3.2 Implementar el scheduler de deadlines absolutos anclado a `samples_generated` del audio con re-anclaje cada ~1 s. Verificar con test de reloj falso (no acumula atraso; los flips tardíos se saltan) y manualmente contra el pulso isocrónico audible.
- [ ] 3.3 Cerrar el modo cuando el audio se detiene o termina. Verificar manualmente: pulsar Stop y dejar terminar una rampa → la ventana se cierra sola.

## 4. UI: botón, estados, sustituto y armónico

- [ ] 4.1 Botón "Modo visual" con estado visible (exacto/aproximado/armónico/no disponible + razón) que se actualiza al cambiar ritmo, categoría o barrido de rampa. Verificar: en 59.8 el preset de 40 Hz aparece bloqueado con razón; 10 Hz aparece exacto.
- [ ] 4.2 Ofrecer el sustituto al máximo real ("usar 29.9 Hz") a un clic cuando el ritmo no está disponible, etiquetado como frecuencia distinta a la pedida. Verificar manual en la pantalla del autor (40 Hz → sustituto 29.9 exacto).
- [ ] 4.3 Modo armónico opt-in (flag avanzado, apagado por defecto) con etiqueta experimental y aviso de la componente adicional ~19.9 Hz. Verificar: sin flag no aparece; con flag, 40 Hz en 59.8 usa período de 3 fotogramas y etiqueta "≈39.87 Hz por armónico".
- [ ] 4.4 Feedback de potencia: etiquetas por estado (jitter en milisegundos en aproximados, menor potencia en armónico, nota en intensidad cómoda). Verificar con tests unitarios de la lógica de etiquetas y comprobación visual en la app.

## 5. Seguridad e intensidad

- [ ] 5.1 Aviso de fotosensibilidad con aceptación explícita persistente la primera vez. Verificar: borrar la clave en `config.json` → reaparece el aviso; sin aceptar, el modo no arranca.
- [ ] 5.2 Intensidad cómoda por defecto y brillante opt-in con advertencia de contraste. Verificar: config nuevo → cómoda; al elegir brillante aparece la advertencia y el parpadeo usa máximo contraste.
- [ ] 5.3 Declaración visible de "no es dispositivo médico ni tratamiento" y ausencia de autoarranque al iniciar audio. Verificar manualmente leyendo la UI del modo visual y arrancando audio sin tocar el botón.

## 6. Documentación

- [ ] 6.1 Documentar en `README.md` y `LEEME.md`: uso del modo visual, estados del gate, aviso PSE (incluida la advertencia del preset de 16 Hz por caer en la banda 15–25 Hz) y cómo desbloquear 40 Hz real (monitor ≥120 Hz o hardware externo). Verificar: seguir las instrucciones del doc reproduce el flujo real sin pasos faltantes.

## 7. Verificación de integración

- [ ] 7.1 En el hardware del autor (59.8 Hz): medir tasa lograda y jitter con audio sonando, comprobar salida con cualquier tecla, cierre al parar el audio, bloqueo de 40 Hz y que `python SourceCode.py --debug` sigue en verde (sin regresión del motor de audio). Registrar resultados en una nota de verificación dentro del change.

## Workflow follow-up

- Archivar el change cuando la revisión esté satisfecha (`openspec archive modo-visual-estroboscopico`).
- Verificar que `openspec/specs/estimulacion-visual/spec.md` existe con las requirements archivadas.
