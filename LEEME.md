<div align="center">

# 🧠 NeuralBeat — Guía rápida en español

**Generador de tonos binaurales, monaurales e isocrónicos** con verificación científica de frecuencias.

*100% local y privado: sin internet, sin cuentas, sin telemetría.*

</div>

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
git clone https://github.com/Aegean-E/NeuralBeat.git
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
| `SourceCode.py` | Aplicación principal (interfaz + motor de audio) |
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
