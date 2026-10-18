# Spec Delta

## Purpose

Modo de estimulación visual estroboscópica a pantalla completa, sincronizado con el audio generado, que solo entrega ritmos que la pantalla puede reproducir con precisión verificable, con feedback honesto de potencia y salvaguardas fotosensibles.

## ADDED Requirements

### Requirement: Modo visual acoplado al audio
El modo visual SHALL abrirse a pantalla completa solo mientras hay audio reproduciéndose y SHALL parpadear al ritmo efectivo del audio (binaural: |derecha−izquierda|; isocrónico: `pulse_hz`; rampa: valor del barrido en curso). El arranque SHALL alinear la fase visual con el pulso de audio.

#### Scenario: Arranque con audio sonando
- **WHEN** el usuario activa el modo visual con audio reproduciéndose
- **THEN** se abre la ventana a pantalla completa y el parpadeo coincide en ritmo y fase con el pulso de audio

#### Scenario: Activación sin audio
- **WHEN** el usuario intenta activar el modo visual sin audio reproduciéndose
- **THEN** el control no inicia el modo y explica que requiere audio sonando

#### Scenario: El audio termina
- **WHEN** el audio se detiene o termina (incluido fade-out o fin de rampa)
- **THEN** el modo visual se cierra y restaura la ventana principal

### Requirement: Capacidad de pantalla medida en tiempo de ejecución
El sistema SHALL medir el refresh efectivo de la pantalla con reloj monótono (alternando fotogramas y cronometrando cada presentación) y SHALL derivar de esa medición los ritmos soportados, sin constantes de hardware fijas. La medición SHALL persistir en la configuración y SHALL poder repetirse a demanda.

#### Scenario: Medición en pantalla de 59.8 Hz
- **WHEN** se calibra una pantalla que entrega 59.8 presentaciones por segundo
- **THEN** la capacidad reportada tiene máximo exacto 29.9 Hz y 40 Hz no disponible

#### Scenario: Cambio a monitor mejor
- **WHEN** el usuario conecta un monitor de 120 Hz y recalibra
- **THEN** 40 Hz pasa a estar disponible como exacto sin cambios de código

#### Scenario: Recalibración a demanda
- **WHEN** existe una medición previa y el usuario pide recalibrar
- **THEN** el sistema descarta la medición anterior y la reemplaza por la nueva

### Requirement: Gate de soporte y estados visibles
El botón del modo visual SHALL mostrar antes de arrancar su estado: exacto, aproximado, armónico experimental o no disponible, con razón legible cuando no está disponible. El sistema SHALL negarse a iniciar cualquier ritmo cuya fundamental exceda la mitad del refresh medido.

#### Scenario: Ritmo exacto
- **WHEN** el ritmo pedido divide entero el refresh medido (p. ej. 29.9 Hz en 59.8)
- **THEN** el estado mostrado es "exacto"

#### Scenario: Ritmo no disponible
- **WHEN** el ritmo pedido (p. ej. 40 Hz) excede la mitad del refresh medido (29.9 Hz)
- **THEN** el estado es "no disponible" con la razón a la vista y el parpadeo no arranca

#### Scenario: Ritmo aproximado
- **WHEN** el ritmo pedido no divide entero el refresh pero es alcanzable con un patrón periódico de fotogramas
- **THEN** el estado es "aproximado" e informa el jitter esperado en milisegundos

#### Scenario: Gate sobre rampa
- **WHEN** el preset activo usa rampa cuyo barrido cruza el máximo soportado
- **THEN** el gate se evalúa con el peor punto del barrido, no con el valor inicial

### Requirement: Feedback de potencia
La interfaz SHALL indicar cuando la estimulación visual entrega menos potencia que la configuración ideal y SHALL nombrar la causa: interpolación con jitter, modo armónico o intensidad cómoda.

#### Scenario: Modo armónico activo
- **WHEN** el modo armónico experimental está activo
- **THEN** la interfaz indica potencia menor que la nominal y la componente adicional que introduce

#### Scenario: Intensidad cómoda
- **WHEN** la intensidad está en cómoda
- **THEN** la interfaz indica que la respuesta visual esperada es menor que en intensidad brillante

### Requirement: Sustituto al máximo real
Cuando el ritmo pedido no sea reproducible, el sistema SHALL ofrecer a un clic el ritmo exacto más alto soportado y SHALL etiquetarlo como una frecuencia distinta a la pedida.

#### Scenario: Ofrecimiento para 40 Hz bloqueado
- **WHEN** 40 Hz está no disponible en una pantalla de 59.8 Hz
- **THEN** el modo visual ofrece "usar 29.9 Hz" y al aceptarlo arranca etiquetado como 29.9 Hz exacto

### Requirement: Modo armónico experimental
El sistema SHALL ofrecer, desactivado por defecto y solo como elección explícita, un patrón de pulsos a un divisor entero del refresh cuyo armónico aproxime el ritmo pedido, etiquetado como experimental y no equivalente al ritmo nominal.

#### Scenario: 40 Hz por segundo armónico
- **WHEN** el usuario habilita el modo armónico para un ritmo de 40 Hz en una pantalla de 59.8 Hz
- **THEN** el parpadeo usa período de 3 fotogramas (19.93 Hz) y la interfaz lo etiqueta como ≈39.87 Hz por armónico, experimental

### Requirement: Salida inmediata
El modo visual SHALL cerrarse de inmediato ante cualquier tecla, ante un clic, y cuando el audio se detenga o termine.

#### Scenario: Cualquier tecla
- **WHEN** el usuario presiona cualquier tecla durante el modo visual
- **THEN** el modo se cierra y la ventana principal recupera el foco

#### Scenario: Clic en pantalla
- **WHEN** el usuario hace clic durante el modo visual
- **THEN** el modo se cierra

### Requirement: Salvaguardas fotosensibles
Antes del primer uso el sistema SHALL mostrar un aviso de epilepsia fotosensible y SHALL exigir una aceptación explícita persistente. El modo visual MUST NOT autoiniciarse y SHALL declarar que no es dispositivo médico ni tratamiento.

#### Scenario: Primer uso
- **WHEN** el usuario activa el modo visual por primera vez
- **THEN** aparece el aviso de fotosensibilidad y el modo solo arranca tras aceptación explícita

#### Scenario: Sin autoarranque
- **WHEN** comienza la reproducción de audio
- **THEN** el modo visual no arranca solo en ningún caso

#### Scenario: Declaración visible
- **WHEN** el usuario usa el modo visual
- **THEN** encuentra la declaración de que no es dispositivo médico ni tratamiento

### Requirement: Intensidad configurable
El sistema SHALL ofrecer intensidad cómoda (por defecto) y brillante (opt-in), y SHALL advertir que mayor contraste implica mayor respuesta visual esperada.

#### Scenario: Cambio a brillante
- **WHEN** el usuario elige intensidad brillante
- **THEN** la interfaz advierte del mayor contraste y el parpadeo usa el máximo contraste

#### Scenario: Valor por defecto
- **WHEN** no existe una elección previa
- **THEN** el modo visual usa intensidad cómoda
