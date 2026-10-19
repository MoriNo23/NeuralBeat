<div align="center">

# 🧠 NeuralBeat — Guía rápida en español

**Generador de tonos binaurales, monaurales e isocrónicos** con verificación científica de frecuencias.

*100% local y privado: sin internet, sin cuentas, sin telemetría.*

</div>

> ℹ️ **Fork:** este repositorio es un fork de [Aegean-E/NeuralBeat](https://github.com/Aegean-E/NeuralBeat) mantenido por [MoriNo23](https://github.com/MoriNo23/NeuralBeat). No es el proyecto original: los issues y pull requests de este repositorio los atiende el mantenedor del fork.

---

## 📋 Requisitos previos

- **Python 3.8 o superior** (`python3 --version` para comprobarlo)
- **En Linux** — librería de audio PortAudio:

  ```bash
  sudo apt install libportaudio2
  ```

  (En Arch/Manjaro: `sudo pacman -S portaudio`. En Windows y macOS normalmente no hace falta nada extra.)
- **Auriculares estéreo** — imprescindibles para los tonos binaurales; los monaurales e isocrónicos funcionan con altavoces.

---

## 📦 Instalación paso a paso

```bash
# 1. Clonar el repositorio
git clone https://github.com/MoriNo23/NeuralBeat.git
cd NeuralBeat

# 2. Crear un entorno virtual (recomendado)
python3 -m venv venv
source venv/bin/activate        # Linux / macOS
# .\venv\Scripts\activate       # Windows (PowerShell)

# 3. Instalar las dependencias
pip install -r requirements.txt
```

Esto instalará: `numpy`, `scipy`, `sounddevice`, `ttkbootstrap` y `matplotlib`.

---

## 🚀 Ejecutar la aplicación

Con el entorno virtual activado, desde la carpeta del proyecto:

```bash
python SourceCode.py
```

Se abrirá la ventana principal. Ajusta las frecuencias y pulsa **Generate Beat**.

> ℹ️ **Nota:** la primera vez puede aparecer el mensaje
> *"Matplotlib is building the font cache; this may take a moment."*
> Es normal — matplotlib construye su caché de fuentes una sola vez. Espera unos segundos.

### Uso básico

1. Elige el tipo de tono: **Binaural / Monaural** o **Isocrónico**.
2. Configura las frecuencias (p. ej. oreja izquierda 432 Hz, derecha 440 Hz → batido de 8 Hz).
3. Ajusta el volumen de cada canal.
4. Opcional: añade ruido de fondo (blanco, rosa o marrón) o activa **Enable Ramp** para transiciones graduales entre estados.
5. Pulsa **Generate Beat**. Para detener, **Stop**.

---

## ⚡ Modo visual estroboscópico

Convierte el motor de audio en un estímulo audiovisual: una ventana a pantalla
completa parpadea al ritmo del audio (binaural/monaural: |derecha − izquierda|;
isocrónico: la tasa de pulso; rampa: el valor del barrido en curso, con el
gate evaluado en el *peor* punto del barrido).

1. Arranca el audio con **Generate Beat** (el modo nunca se auto-inicia)
2. Pulsa **Modo visual - ...** en la barra "Modo visual (estroboscopio)"
3. La primera vez se pide aceptar un aviso de epilepsia fotosensible y
   (opcional) calibrar la pantalla (~2 s a pantalla completa)
4. Cualquier tecla o clic cierra el modo al instante; parar o terminar el
   audio lo cierra automáticamente

El botón muestra siempre el estado del gate antes de arrancar:

| Estado | Significado |
|---|---|
| **exacto** | El ritmo cae en un número entero de fotogramas (p. ej. 29,9 Hz en un panel de 59,8 Hz; 40 Hz en uno de 120 Hz). Jitter cero. Si la frecuencia efectiva difiere de la pedida se re-etiqueta (p. ej. 10 Hz → 9,97 Hz) |
| **aproximado** | Se emite con un patrón periódico de fotogramas (ventana ≤ 1 s) y se informa el jitter esperado (~1 fotograma) en milisegundos |
| **armónico** | *Experimental, opt-in*: pulsos a un divisor entero del refresco cuyo 2º armónico aproxima el ritmo pedido (p. ej. 40 Hz pedidos en ~60 Hz → pulsos de 19,93 Hz, 2º armónico ≈39,87 Hz). Menos potencia y añade una componente en la fundamental |
| **no disponible** | El ritmo supera la mitad del refresco medido. Nunca se emite "a la brava": en un panel de 60 Hz, forzar 40 Hz alíasea a ~19,8 Hz (banda equivocada y dentro de la zona de riesgo fotosensible) |

Si el ritmo no está disponible, se ofrece a un clic el ritmo exacto más alto
que soporta tu pantalla (p. ej. *usar 29,9 Hz* en un panel de 59,8 Hz),
etiquetado como una frecuencia **distinta a la pedida**. Con el flag
experimental activado (Settings → Visual → Modo armónico experimental)
también se ofrece la alternativa armónica.

En **Settings → Visual**:
- **Recalibrar pantalla**: vuelve a medir el refresco real (mediana de flips
  cronometrados, jitter p95) y recalcula el gate. Mejor hardware ⇒ mejor
  capacidad sin cambios de código.
- **Intensidad**: *cómoda* (por defecto, contraste moderado, menor respuesta
  visual esperada) o *brillante* (opt-in, contraste máximo, con advertencia).

**Cómo desbloquear 40 Hz reales**: un panel de clase 60 Hz no puede
producirlos físicamente (la fundamental está limitada a refresco/2). Usa un
monitor de 120 Hz o más (recalibra tras conectarlo: 40 Hz pasa a *exacto* por
sí solo) o hardware externo dedicado (gafas LED de estrobo). Ni pantallas de
teléfono ni trucos de software crean resolución temporal entre fotogramas.

**Seguridad**: las luces parpadeantes pueden provocar convulsiones en
personas con epilepsia fotosensible; el riesgo máximo está en la banda
15-25 Hz (los presets de 16 Hz incluidos caen dentro). No uses el modo visual
si tú o un familiar tienen epilepsia. NeuralBeat y su modo visual **no son un
dispositivo médico ni un tratamiento**. La intensidad cómoda es el valor por
defecto; ante cualquier malestar, ciérralo con cualquier tecla.

---

## 🔬 Modo verificación científica

Comprueba que el audio generado es matemáticamente exacto (análisis FFT, amplitud, separación estéreo):

```bash
python SourceCode.py --debug
```

Genera una señal de prueba de 1 segundo e imprime un reporte completo en la terminal.

---

## 🧪 Ejecutar los tests

```bash
pip install pytest    # solo la primera vez
python run_tests.py
```

---

## 🛠 Solución de problemas

| Problema | Solución |
|---|---|
| `_tkinter.TclError: unknown option "-bootstyle"` | Ya está corregido en este repositorio: el interruptor *Enable Ramp* usa `tb.Checkbutton` de ttkbootstrap en lugar del `ttk` estándar. |
| Error de PortAudio o no hay sonido en Linux | Instala la librería: `sudo apt install libportaudio2` |
| *"Matplotlib is building the font cache"* | Normal la primera vez; espera a que termine. |
| No se oye nada | Revisa el dispositivo de salida y el volumen del sistema. Los tonos binaurales requieren auriculares estéreo. |
| La app no abre (Linux/Wayland) | Asegúrate de tener Tk funcionando: `python3 -c "import tkinter; tkinter.Tk()"` |

---

## 📁 Estructura del proyecto

| Archivo / carpeta | Descripción |
|---|---|
| `SourceCode.py` | Aplicación principal (interfaz + motor de audio + modo visual) |
| `visual.py` | Núcleo del modo visual: capacidad, patrones, calibración y scheduler |
| `presets.py` | Presets de frecuencias integrados |
| `verification.py` | Módulo de validación científica |
| `run_tests.py` | Ejecutor de la suite de tests |
| `tests/` | Pruebas unitarias |
| `requirements.txt` | Dependencias del proyecto |

---

## 🎨 Temas disponibles

Cámbialos desde el menú **Settings** dentro de la aplicación:

| Tema | Tipo |
|---|---|
| `darkly` (por defecto) | Oscuro |
| `superhero` | Oscuro |
| `flatly` | Claro |

---

## 📚 Más información

Para la guía completa (ciencia detrás de los batidos cerebrales, tabla de presets, metodología de verificación, FAQ y licencia), consulta el [`README.md`](README.md) (en inglés).

**Licencia:** Apache 2.0 — ver el archivo `LICENSE`.
