import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
import time
import json
from pathlib import Path
from tkinter import filedialog
import logging
import threading
import os
import subprocess
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
from scipy import signal
from scipy.io import wavfile
import ttkbootstrap as tb

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import presets
import verification
import visual

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# =============================================================================
# Global Application State
# =============================================================================

osc_merge_var = None
live_status_after_id = None
play_mode = "manual"  # "manual" or "ramp"
beat_type_var = None  # "binaural", "monaural", or "isochronic"

# UI widget globals: se crean en main() y se declaran aqui a nivel de modulo
# (mismo patron que beat_type_var/osc_merge_var) para que los tests puedan
# parchearlos con unittest.mock.patch antes de que exista la ventana.
left_frequency_entry = None
right_frequency_entry = None
left_volume_entry = None
right_volume_entry = None
left_waveform_var = None
right_waveform_var = None
noise_type_var = None
noise_volume_entry = None
ramp_enabled_var = None
carrier_entry = None
start_beat_entry = None
end_beat_entry = None
ramp_minutes_entry = None
binaural_monaural_frame = None
isochronic_beats_frame = None

# Defaults
ramp_carrier_hz = 432.0
ramp_start_beat_hz = 20.0
ramp_end_beat_hz = 3.0
ramp_duration_s = 30.0 * 60.0
manual_left_hz = 432.0
manual_right_hz = 432.0

APP_DIR = Path.home() / ".neuralbeat"
CONFIG_PATH = APP_DIR / "config.json"

# Visualizer state
osc_window = None
visualizer_canvas = None
visualizer_ax = None
line_left = None
line_right = None
OSC_BUFFER_SECONDS = 0.05
osc_plot_buffer_l = None
osc_plot_buffer_r = None

OSC_COLOR_PALETTES = {
    "Cyan / Magenta": {
        "dark": ("#00FFFF", "#FF00FF"),
        "light": ("#008B8B", "#8B008B")
    },
    "Green / Yellow": {
        "dark": ("#00FF00", "#FFFF00"),
        "light": ("#006400", "#BDB76B")
    },
    "Red / Blue": {
        "dark": ("#FF4500", "#1E90FF"),
        "light": ("#DC143C", "#0000CD")
    }
}


waveforms = {
    "Sine": np.sin,
    "Square": signal.square,
    "Sawtooth": signal.sawtooth,
    "Triangle": lambda t: signal.sawtooth(t, width=0.5),
}

# =============================================================================
# Noise Generation
# =============================================================================

class NoiseGenerator:
    """
    Generates blocks of colored noise with state preservation using digital filters.
    """
    def __init__(self):
        # Pink noise filter coeffs (-3dB/octave)
        self.pink_b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
        self.pink_a = [1, -2.494956002, 2.017265875, -0.522189400]
        self.pink_zi = signal.lfilter_zi(self.pink_b, self.pink_a)

        # Brown noise filter coeffs (leaky integrator, -6dB/octave)
        self.brown_b = [1.0]
        self.brown_a = [1.0, -0.999] # Very close to 1 for strong low-pass
        self.brown_zi = signal.lfilter_zi(self.brown_b, self.brown_a)

    def _normalize(self, noise):
        """Normalize noise to have RMS of 1."""
        rms = np.sqrt(np.mean(noise**2))
        if rms > 1e-9:
            return noise / rms
        return noise

    def generate(self, noise_type, n_samples):
        if noise_type == "White":
            return self._normalize(np.random.randn(n_samples))
        elif noise_type == "Pink":
            white = np.random.randn(n_samples)
            noise, self.pink_zi = signal.lfilter(self.pink_b, self.pink_a, white, zi=self.pink_zi)
            return self._normalize(noise)
        elif noise_type == "Brown":
            white = np.random.randn(n_samples)
            noise, self.brown_zi = signal.lfilter(self.brown_b, self.brown_a, white, zi=self.brown_zi)
            return self._normalize(noise)
        return np.zeros(n_samples)

# =============================================================================
# Configuration & Persistence
# =============================================================================

def load_config() -> dict:
    """Loads configuration from the JSON file."""
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        logger.error(f"Error loading config from {CONFIG_PATH}", exc_info=True)
    return {}

def save_config(cfg: dict) -> None:
    """Saves the configuration dictionary to the JSON file."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        logger.error(f"Error saving config to {CONFIG_PATH}", exc_info=True)

config = load_config()
initial_theme = config.get("theme", "darkly")

def _normalize_category(category: str) -> str:
    c = str(category).strip().lower()
    if "binaural" in c or "monaural" in c:
        return "Binaural"
    if "isochronic" in c:
        return "Isochronic"
    raise ValueError("Category must be 'Binaural Beat / Monaural Beat' or 'Isochronic Tone'")

def get_user_presets() -> dict:
    up = config.get("user_presets", {})
    return {
        "Monaural": list(up.get("Monaural", [])),
        "Binaural": list(up.get("Binaural", [])),
        "Isochronic": list(up.get("Isochronic", [])),
    }

def add_user_preset(category: str, label: str, left_hz: float, right_hz: float) -> None:
    category = _normalize_category(category)
    try:
        preset_obj = {
            "label": str(label).strip(),
            "left_hz": float(left_hz),
            "right_hz": float(right_hz),
        }
    except ValueError:
        raise ValueError("Invalid numeric value for frequencies.")
    if not preset_obj["label"]:
        raise ValueError("Preset Name Cannot be Empty")

    up = get_user_presets()
    up[category].append(preset_obj)
    config["user_presets"] = up
    save_config(config)

def remove_user_preset(category: str, label: str) -> bool:
    category = _normalize_category(category)
    up = get_user_presets()
    label = str(label).strip()
    for i, p in enumerate(up[category]):
        if str(p.get("label", "")).strip() == label:
            up[category].pop(i)
            config["user_presets"] = up
            save_config(config)
            return True
    return False

def get_all_presets() -> dict:
    up = get_user_presets()
    return {
        "Monaural": list(presets.MONAURAL_PRESETS) + up["Monaural"],
        "Binaural": list(presets.BINAURAL_PRESETS) + up["Binaural"],
        "Isochronic": list(presets.ISOCHRONIC_PRESETS) + up["Isochronic"],
    }

# =============================================================================
# Audio Engine & DSP
# =============================================================================

def clamp(value, lo, hi):
    """Clamps a value between lo and hi."""
    return max(lo, min(hi, value))

def validate_audio_params(freq_l, freq_r, vol_l, vol_r, duration=None):
    """Validates audio parameters (frequencies, volumes, duration)."""
    if not (20.0 <= freq_l <= 20000.0):
        return "Frequency must be between 20 Hz and 20000 Hz."
    if not (20.0 <= freq_r <= 20000.0):
        return "Frequency must be between 20 Hz and 20000 Hz."
    if not (0.0 <= vol_l <= 100.0):
        return "Volume must be between 0% and 100%."
    if not (0.0 <= vol_r <= 100.0):
        return "Volume must be between 0% and 100%."
    if duration is not None and duration <= 0:
        return "Duration must be positive."
    return None

def _compute_ramped_beat_hz(elapsed_s: float, start_beat_hz: float, end_beat_hz: float, ramp_s: float) -> float:
    """Calculates the current beat frequency based on ramp progress."""
    if ramp_s <= 0:
        return end_beat_hz
    x = clamp(elapsed_s / ramp_s, 0.0, 1.0)
    return start_beat_hz + (end_beat_hz - start_beat_hz) * x

@dataclass
class AudioConfig:
    sample_rate: int
    left_volume: float
    right_volume: float
    left_waveform: str
    right_waveform: str
    noise_type: str
    noise_volume: float
    use_ramp: bool
    left_frequency: float
    right_frequency: float
    carrier_hz: float
    start_beat_hz: float
    end_beat_hz: float
    ramp_duration_s: float
    beat_type: str = "binaural"

def get_audio_config_from_ui() -> AudioConfig:
    """Reads values from UI entries and returns an AudioConfig object."""
    try:
        left_volume_val = float(left_volume_entry.get())
        right_volume_val = float(right_volume_entry.get())
        noise_volume_val = float(noise_volume_entry.get())
    except ValueError:
        raise ValueError("Please enter valid numeric values for volume.")

    left_volume = clamp(left_volume_val / 100.0, 0.0, 1.0)
    right_volume = clamp(right_volume_val / 100.0, 0.0, 1.0)
    noise_volume = clamp(noise_volume_val / 100.0, 0.0, 1.0)

    left_waveform = left_waveform_var.get()
    right_waveform = right_waveform_var.get()
    noise_type = noise_type_var.get()
    use_ramp = bool(ramp_enabled_var.get())
    sample_rate = 44100
    beat_type = beat_type_var.get() if beat_type_var else "binaural"

    if use_ramp:
        try:
            r_carrier = float(carrier_entry.get())
            r_start = float(start_beat_entry.get())
            r_end = float(end_beat_entry.get())
            r_min = float(ramp_minutes_entry.get())
        except ValueError:
            raise ValueError("Please enter valid numeric values for ramp settings.")

        if not (20.0 <= r_carrier <= 20000.0):
             raise ValueError("Carrier frequency must be between 20 Hz and 20000 Hz.")
        if not (0.1 <= r_start <= 100.0):
             raise ValueError("Beat frequency must be between 0.1 Hz and 100 Hz.")
        if not (0.1 <= r_end <= 100.0):
             raise ValueError("Beat frequency must be between 0.1 Hz and 100 Hz.")

        ramp_duration_s = max(0.0, r_min * 60.0)

        return AudioConfig(
            sample_rate=sample_rate,
            left_volume=left_volume,
            right_volume=right_volume,
            left_waveform=left_waveform,
            right_waveform=right_waveform,
            noise_type=noise_type,
            noise_volume=noise_volume,
            use_ramp=True,
            left_frequency=0.0,
            right_frequency=0.0,
            carrier_hz=r_carrier,
            start_beat_hz=r_start,
            end_beat_hz=r_end,
            ramp_duration_s=ramp_duration_s,
            beat_type=beat_type
        )
    else:
        try:
            m_left = float(left_frequency_entry.get())
            m_right = float(right_frequency_entry.get())
        except ValueError:
            raise ValueError("Please enter valid numeric values for frequencies.")

        if beat_type == "isochronic":
            if not (0.1 <= m_left <= 100.0):
                raise ValueError("Beat frequency must be between 0.1 Hz and 100 Hz for isochronic tones.")
            if not (20.0 <= m_right <= 20000.0):
                raise ValueError("Carrier frequency must be between 20 Hz and 20000 Hz.")
        else:
            err = validate_audio_params(m_left, m_right, left_volume_val, right_volume_val)
            if err:
                raise ValueError(err)

        carrier_hz = m_right if beat_type == "isochronic" else 0.0

        return AudioConfig(
            sample_rate=sample_rate,
            left_volume=left_volume,
            right_volume=right_volume,
            left_waveform=left_waveform,
            right_waveform=right_waveform,
            noise_type=noise_type,
            noise_volume=noise_volume,
            use_ramp=False,
            left_frequency=m_left,
            right_frequency=m_right,
            carrier_hz=carrier_hz,
            start_beat_hz=0.0,
            end_beat_hz=0.0,
            ramp_duration_s=0.0,
            beat_type=beat_type
        )

class BinauralGenerator:
    """
    Generates binaural or monaural beats based on the provided AudioConfig.
    Handles waveform generation, ramping, and soft limiting.
    """
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self.phase_l = 0.0
        self.phase_r = 0.0
        self.samples_generated = 0
        self.ramp_s = cfg.ramp_duration_s

        # Initialize noise generator if needed
        if self.cfg.noise_type != "None" and self.cfg.noise_volume > 0:
            self.noise_gen = NoiseGenerator()
        else:
            self.noise_gen = None

        # Resolve waveform functions
        # Default to Sine if not found to prevent crashes
        self.left_wave_func = waveforms.get(cfg.left_waveform, np.sin)
        self.right_wave_func = waveforms.get(cfg.right_waveform, np.sin)

        self.drive = 2.5
        self.tanh_drive = np.tanh(self.drive)

        # Fade configuration
        self.fade_in_len = int(0.02 * cfg.sample_rate) # 20 ms
        self.fade_out_len = int(0.02 * cfg.sample_rate) # 20 ms
        self.stopping = False
        self.fade_out_counter = 0
        self.is_finished = False

    def request_stop(self):
        """Signal the generator to start fading out."""
        self.stopping = True

    def generate_block(self, frames: int) -> np.ndarray:
        # Time array for this block (seconds relative to start of stream)
        # Using float64 for time accumulation to prevent jitter over long sessions, though inputs are float
        current_time = self.samples_generated / self.cfg.sample_rate

        # Calculate frequencies per sample
        if self.cfg.use_ramp:
            # Vectorized ramp calculation
            # Create global time array for this block
            t_global = current_time + np.arange(frames, dtype=np.float64) / self.cfg.sample_rate

            if self.ramp_s <= 0:
                 beat_hz = np.full(frames, self.cfg.end_beat_hz, dtype=np.float64)
            else:
                 # Linear interpolation with clamping
                 progress = np.clip(t_global / self.ramp_s, 0.0, 1.0)
                 beat_hz = self.cfg.start_beat_hz + (self.cfg.end_beat_hz - self.cfg.start_beat_hz) * progress

            lf_array = self.cfg.carrier_hz - (beat_hz / 2.0)
            rf_array = self.cfg.carrier_hz + (beat_hz / 2.0)

            # Enforce positive frequency
            lf_array = np.maximum(0.0, lf_array)
            rf_array = np.maximum(0.0, rf_array)

            # Calculate phase increments: 2 * pi * f / sr
            inc_l = (2.0 * np.pi * lf_array / self.cfg.sample_rate)
            inc_r = (2.0 * np.pi * rf_array / self.cfg.sample_rate)

            # Calculate cumulative phase shift
            # We start at self.phase_l. Sample 0 is at self.phase_l.
            # Sample n is at self.phase_l + sum(inc[0]...inc[n-1])
            # np.cumsum returns [inc0, inc0+inc1, ...]. We shift it.

            phase_shift_l = np.concatenate(([0.0], np.cumsum(inc_l)[:-1]))
            phase_shift_r = np.concatenate(([0.0], np.cumsum(inc_r)[:-1]))

            phase_vec_l = self.phase_l + phase_shift_l
            phase_vec_r = self.phase_r + phase_shift_r

            # Calculate next block seed phase
            # Total change over this block is sum of all increments
            self.phase_l = (self.phase_l + np.sum(inc_l)) % (2.0 * np.pi)
            self.phase_r = (self.phase_r + np.sum(inc_r)) % (2.0 * np.pi)

        else:
            # Constant frequency optimization
            # Avoid full array allocation and cumsum for constant frequency

            freq_l = max(0.0, self.cfg.left_frequency)
            freq_r = max(0.0, self.cfg.right_frequency)

            # Phase increment per sample
            inc_l = (2.0 * np.pi * freq_l / self.cfg.sample_rate)
            inc_r = (2.0 * np.pi * freq_r / self.cfg.sample_rate)

            # Create time vector for this block (0, 1, ..., frames-1)
            t_vec = np.arange(frames, dtype=np.float64)

            # phase[n] = phase_start + n * inc
            phase_vec_l = self.phase_l + t_vec * inc_l
            phase_vec_r = self.phase_r + t_vec * inc_r

            # Update phase for next block
            self.phase_l = (self.phase_l + frames * inc_l) % (2.0 * np.pi)
            self.phase_r = (self.phase_r + frames * inc_r) % (2.0 * np.pi)

        # Generate Waveforms
        left = self.cfg.left_volume * self.left_wave_func(phase_vec_l)
        right = self.cfg.right_volume * self.right_wave_func(phase_vec_r)

        stereo = np.column_stack((left, right))

        # Generate and mix noise before limiting
        if self.noise_gen:
            noise = self.noise_gen.generate(self.cfg.noise_type, frames)
            # Add mono noise to both channels using broadcasting
            stereo += (noise * self.cfg.noise_volume)[:, np.newaxis]

        # Stateless soft limiter/saturator
        stereo = np.tanh(stereo * self.drive) / self.tanh_drive
        stereo = np.clip(stereo, -1.0, 1.0)

        # Apply Fade In
        start_idx = self.samples_generated
        end_idx = start_idx + frames

        if start_idx < self.fade_in_len:
            # Generate ramp for fade in
            ramp_in = np.arange(start_idx, end_idx, dtype=np.float32) / self.fade_in_len
            ramp_in = np.clip(ramp_in, 0.0, 1.0)
            stereo *= ramp_in[:, np.newaxis]

        # Apply Fade Out if stopping
        if self.stopping:
            # Calculate remaining fade out samples
            remaining = self.fade_out_len - self.fade_out_counter

            if remaining <= 0:
                stereo.fill(0)
                self.is_finished = True
                self.samples_generated += frames
                return stereo

            # Generate fade out ramp
            t_fade = np.arange(self.fade_out_counter, self.fade_out_counter + frames, dtype=np.float32)
            ramp_out = 1.0 - (t_fade / self.fade_out_len)
            ramp_out = np.clip(ramp_out, 0.0, 1.0)

            stereo *= ramp_out[:, np.newaxis]

            self.fade_out_counter += frames

            if self.fade_out_counter >= self.fade_out_len:
                self.is_finished = True
                # Ensure silence after fade
                cutoff = int(remaining)
                if cutoff < frames:
                    stereo[cutoff:] = 0

        self.samples_generated += frames
        return stereo.astype(np.float32, copy=False)


class IsochronicGenerator:
    """
    Generates isochronic tones - rhythmic pulses of sound at a specific beat frequency.
    The carrier tone pulses on and off at the beat rate with equal intensity on both channels.
    """
    def __init__(self, cfg: AudioConfig):
        self.cfg = cfg
        self.phase = 0.0
        self.samples_generated = 0
        self.ramp_s = cfg.ramp_duration_s

        if self.cfg.noise_type != "None" and self.cfg.noise_volume > 0:
            self.noise_gen = NoiseGenerator()
        else:
            self.noise_gen = None

        self.wave_func = waveforms.get(cfg.left_waveform, np.sin)

        self.drive = 2.5
        self.tanh_drive = np.tanh(self.drive)

        self.fade_in_len = int(0.02 * cfg.sample_rate)
        self.fade_out_len = int(0.02 * cfg.sample_rate)
        self.stopping = False
        self.fade_out_counter = 0
        self.is_finished = False

    def request_stop(self):
        self.stopping = True

    def generate_block(self, frames: int) -> np.ndarray:
        current_time = self.samples_generated / self.cfg.sample_rate

        if self.cfg.use_ramp:
            t_global = current_time + np.arange(frames, dtype=np.float64) / self.cfg.sample_rate

            if self.ramp_s <= 0:
                beat_hz = np.full(frames, self.cfg.end_beat_hz, dtype=np.float64)
            else:
                progress = np.clip(t_global / self.ramp_s, 0.0, 1.0)
                beat_hz = self.cfg.start_beat_hz + (self.cfg.end_beat_hz - self.cfg.start_beat_hz) * progress

            beat_hz = np.maximum(0.1, beat_hz)
            carrier_hz = np.full(frames, self.cfg.carrier_hz, dtype=np.float64)
        else:
            beat_hz = np.full(frames, max(0.1, self.cfg.left_frequency), dtype=np.float64)
            carrier_hz = np.full(frames, max(20.0, self.cfg.carrier_hz), dtype=np.float64)

        inc = (2.0 * np.pi * carrier_hz / self.cfg.sample_rate)
        phase_shift = np.concatenate(([0.0], np.cumsum(inc)[:-1]))
        phase_vec = self.phase + phase_shift
        self.phase = (self.phase + np.sum(inc)) % (2.0 * np.pi)

        carrier_wave = self.wave_func(phase_vec)

        period_samples = self.cfg.sample_rate / beat_hz
        pulse = np.mod(np.arange(frames, dtype=np.float64) + self.samples_generated, period_samples) < (period_samples * 0.5)

        mono = self.cfg.left_volume * carrier_wave * pulse.astype(np.float64)

        stereo = np.column_stack((mono, mono))

        if self.noise_gen:
            noise = self.noise_gen.generate(self.cfg.noise_type, frames)
            stereo += (noise * self.cfg.noise_volume)[:, np.newaxis]

        stereo = np.tanh(stereo * self.drive) / self.tanh_drive
        stereo = np.clip(stereo, -1.0, 1.0)

        start_idx = self.samples_generated
        if start_idx < self.fade_in_len:
            ramp_in = np.arange(start_idx, start_idx + frames, dtype=np.float32) / self.fade_in_len
            ramp_in = np.clip(ramp_in, 0.0, 1.0)
            stereo *= ramp_in[:, np.newaxis]

        if self.stopping:
            remaining = self.fade_out_len - self.fade_out_counter
            if remaining <= 0:
                stereo.fill(0)
                self.is_finished = True
                self.samples_generated += frames
                return stereo

            t_fade = np.arange(self.fade_out_counter, self.fade_out_counter + frames, dtype=np.float32)
            ramp_out = 1.0 - (t_fade / self.fade_out_len)
            ramp_out = np.clip(ramp_out, 0.0, 1.0)

            stereo *= ramp_out[:, np.newaxis]

            self.fade_out_counter += frames

            if self.fade_out_counter >= self.fade_out_len:
                self.is_finished = True
                cutoff = int(remaining)
                if cutoff < frames:
                    stereo[cutoff:] = 0

        self.samples_generated += frames
        return stereo.astype(np.float32, copy=False)


class AudioEngine:
    """
    Manages the audio playback stream using sounddevice.
    Handles thread safety for starting and stopping playback.
    """
    def __init__(self):
        self._stream = None
        self.generator = None
        self._lock = threading.Lock()
        self._data_lock = threading.Lock()
        self.is_playing = False
        self.start_time = 0.0
        self.current_config = None
        self.last_block = None

    def start(self, cfg: AudioConfig):
        self.stop()

        with self._lock:
            try:
                if cfg.beat_type == "isochronic":
                    gen = IsochronicGenerator(cfg)
                else:
                    gen = BinauralGenerator(cfg)
                self.generator = gen
                self.current_config = cfg

                def callback(outdata, frames, time, status):
                    if status:
                        logger.warning(f"Audio status: {status}")
                    try:
                        # Generate audio using local 'gen' reference
                        # This avoids race conditions if self.generator is set to None by stop()
                        data = gen.generate_block(frames)
                        outdata[:] = data

                        # Store the last block for visualization
                        with self._data_lock:
                            self.last_block = data.copy()

                        # Check if finished (fade out complete)
                        if gen.is_finished:
                            raise sd.CallbackStop

                    except Exception as e:
                        if not isinstance(e, sd.CallbackStop):
                            logger.error("Audio callback error", exc_info=True)
                        # Silence on error
                        outdata.fill(0)

                self._stream = sd.OutputStream(
                    samplerate=cfg.sample_rate,
                    channels=2,
                    callback=callback,
                    dtype="float32"
                )
                self._stream.start()
                self.is_playing = True
                self.start_time = time.time()
                logger.info("Audio started")
            except Exception as e:
                logger.error("Failed to start audio", exc_info=True)
                self.is_playing = False
                if self._stream:
                    try:
                        self._stream.close()
                    except Exception: pass
                    self._stream = None
                raise e

    def stop(self):
        """Stops audio gracefully with fade out."""
        # 1. Signal stop
        with self._lock:
            if not self.is_playing:
                return

            if self.generator:
                self.generator.request_stop()

        # 2. Wait for stream to finish (fade out)
        # We wait up to 200ms
        for _ in range(20):
             with self._lock:
                 if self.generator and self.generator.is_finished:
                     break
                 # Also check if stream is inactive?
                 # stream.active might be true until callback returns Stop
             time.sleep(0.01)

        # 3. Force stop
        with self._lock:
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    logger.error("Error closing stream", exc_info=True)
                self._stream = None
            self.is_playing = False
            self.generator = None
            with self._data_lock:
                self.last_block = None
            logger.info("Audio stopped")

    def get_elapsed_time(self):
        if self.is_playing:
            return time.time() - self.start_time
        return 0.0
    
    def get_last_block(self):
        with self._data_lock:
            if self.last_block is not None:
                return self.last_block.copy()
        return None

audio_engine = AudioEngine()

def stop_audio():
    global live_status_after_id
    global play_mode

    # El modo visual depende del audio en curso: se cierra antes de pararlo
    if visual_mode_active:
        close_visual_mode("audio detenido")

    # Stop UI update loop
    if live_status_after_id is not None:
        try:
            root.after_cancel(live_status_after_id)
        except Exception:
            logger.error("Error cancelling live status update", exc_info=True)
        live_status_after_id = None

    try:
        audio_engine.stop()
    except Exception as e:
        logger.error(f"Error stopping audio: {e}", exc_info=True)

    play_mode = "manual"


# =============================================================================
# Visual Strobe Mode (openspec: estimulacion-visual)
# =============================================================================

# Estado del modo visual (la ventana y el scheduler viven en el hilo Tk).
visual_mode_active = False
visual_window = None
visual_scheduler = None
visual_after_id = None
visual_lateness_monitor = None
visual_active_cap = None
visual_active_gen = None
visual_active_req = None
visual_beat_clock = None
visual_active_status = None
visual_last_reason = None
visual_status_last_refresh = 0.0
visual_toggle_button = None
visual_status_label = None
visual_intensity_var = None
visual_harmonics_var = None

STATE_BOOTSTYLES = {
    "exacto": "success",
    "aproximado": "warning",
    "armonico": "info",
    "no_disponible": "danger",
}

PHOTOSENSITIVE_WARNING = (
    "ADVERTENCIA DE SEGURIDAD FOTOSENSIBLE\n\n"
    "El modo visual produce parpadeos de luz a pantalla completa.\n"
    "Las luces intermitentes pueden provocar convulsiones en personas con "
    "epilepsia fotosensible. El riesgo es máximo en la banda 15-25 Hz "
    "(donde cae el preset de 16 Hz incluido en esta app).\n\n"
    "No lo uses si tu o alguien de tu familia tiene epilepsia o sensibilidad "
    "a luces parpadeantes; consulta antes a un médico.\n\n"
    "Ante cualquier malestar, cierra el modo de inmediato: cualquier tecla o "
    "clic lo interrumpe.\n\n"
    "NeuralBeat y su modo visual NO son un dispositivo médico ni un "
    "tratamiento.\n\n"
    "¿Entiendes el riesgo y quieres habilitar el modo visual?"
)


def get_visual_settings() -> dict:
    """Seccion visual de la config fusionada con defaults (compatible atras)."""
    return visual.merge_visual_config(config)


def save_visual_setting(key, value) -> None:
    """Persiste una clave de la seccion visual en ~/.neuralbeat/config.json."""
    v = config.get("visual") if isinstance(config.get("visual"), dict) else {}
    v[key] = value
    config["visual"] = v
    save_config(config)


def get_visual_refresh_hz() -> float:
    """Refresco calibrado de la pantalla (default conservador si no hay)."""
    v = get_visual_settings()
    if v["refresh_hz"] and v["refresh_hz"] > 0:
        return v["refresh_hz"]
    return visual.DEFAULT_REFRESH_HZ


def probe_system_refresh_hz():
    """Refresco nominal que reporta el sistema (xrandr). None si no se puede.

    No es una medicion: solo evita el default de 60 Hz cuando la calibracion
    real no es fiable (p. ej. compositor que ignora deadlines).
    """
    try:
        out = subprocess.run(["xrandr", "--current"], capture_output=True,
                             text=True, timeout=3.0).stdout
    except Exception:
        logger.info("Sin xrandr para el refresco del sistema", exc_info=True)
        return None
    return visual.parse_xrandr_refresh_hz(out)


def get_visual_rate_request() -> dict:
    """Resuelve el ritmo visual pedido segun el estado de la UI.

    Devuelve mode ("manual"/"ramp"), beat_type y rate_hz: binaural usa
    |derecha-izquierda|, isocronico usa la tasa de pulso, y la rampa usa el
    PEOR punto del barrido (gate). Lanza ValueError si algo no es numerico.
    """
    bt = beat_type_var.get() if beat_type_var else "binaural"
    if ramp_enabled_var.get():
        try:
            start = float(start_beat_entry.get())
            end = float(end_beat_entry.get())
            minutes = float(ramp_minutes_entry.get())
        except (ValueError, TypeError):
            raise ValueError("Ramp settings must be numeric.")
        worst = max(abs(start), abs(end))
        return {
            "mode": "ramp",
            "beat_type": bt,
            "rate_hz": worst,
            "start_hz": start,
            "end_hz": end,
            "ramp_s": max(0.0, minutes * 60.0),
        }
    try:
        left = float(left_frequency_entry.get())
        right = float(right_frequency_entry.get())
    except (ValueError, TypeError):
        raise ValueError("Frequencies must be numeric.")
    if bt == "isochronic":
        rate = abs(left)
    else:
        rate = abs(right - left)
    return {
        "mode": "manual",
        "beat_type": bt,
        "rate_hz": rate,
        "start_hz": None,
        "end_hz": None,
        "ramp_s": None,
    }


def get_visual_audio_time() -> float:
    """Tiempo de audio del stream activo (reloj maestro: samples_generated)."""
    g = audio_engine.generator
    c = audio_engine.current_config
    if g is None or c is None:
        return 0.0
    return g.samples_generated / c.sample_rate


def compute_visual_capability():
    """(request, VisualCapability) segun la UI y la calibracion actual."""
    req = get_visual_rate_request()
    refresh = get_visual_refresh_hz()
    harmonics = get_visual_settings()["harmonics_enabled"]
    if req["mode"] == "ramp":
        cap = visual.ramp_gate_capability(
            req["start_hz"], req["end_hz"], refresh, harmonics)
    else:
        cap = visual.visual_capability(req["rate_hz"], refresh, harmonics)
    return req, cap


def update_visual_button():
    """Estado visible del boton Modo visual: exacto / aproximado / armonico /
    no disponible + razon y feedback de potencia (openspec: gate honesto)."""
    global visual_last_reason
    if visual_toggle_button is None or visual_status_label is None:
        return
    if visual_mode_active:
        try:
            visual_toggle_button.config(text="Cerrar modo visual", bootstyle="danger")
        except Exception:
            visual_toggle_button.config(text="Cerrar modo visual")
        visual_status_label.config(
            text=visual_active_status or
            "Modo visual activo - cierra con cualquier tecla")
        return
    try:
        req, cap = compute_visual_capability()
    except (ValueError, TypeError):
        try:
            visual_toggle_button.config(text="Modo visual", bootstyle="secondary")
        except Exception:
            visual_toggle_button.config(text="Modo visual")
        visual_status_label.config(text="Modo visual: introduce un ritmo válido")
        return
    label = visual.capability_label(cap, req["rate_hz"])
    if req["mode"] == "ramp":
        label += " - gate por peor punto del barrido"
    note = visual.intensity_note(get_visual_settings()["intensity"])
    if visual_last_reason:
        note = f"{visual_last_reason} - {note}"
        visual_last_reason = None
    state_txt = cap.state.replace("_", " ")
    try:
        visual_toggle_button.config(
            text=f"Modo visual - {state_txt}",
            bootstyle=STATE_BOOTSTYLES.get(cap.state, "secondary"))
    except Exception:
        visual_toggle_button.config(text=f"Modo visual - {state_txt}")
    visual_status_label.config(text=f"Visual: {label} - {note}")


def toggle_visual_mode():
    """Accion del boton Modo visual: gate + consentimiento + arranque.

    Nunca se auto-arranca: solo desde esta accion explicita del usuario.
    """
    if visual_mode_active:
        close_visual_mode()
        return
    if not audio_engine.is_playing:
        # Spec: sin audio sonando no inicia y explica por que
        messagebox.showinfo(
            "Modo visual",
            "El modo visual solo puede abrirse mientras suena audio.\n"
            "Pulsa 'Generate Beat' primero.")
        return
    settings = get_visual_settings()
    if not settings["photosensitive_consent"]:
        if not messagebox.askyesno("Aviso de fotosensibilidad",
                                   PHOTOSENSITIVE_WARNING):
            return
        save_visual_setting("photosensitive_consent", True)
    if not settings["refresh_hz"]:
        if messagebox.askyesno(
                "Calibración de pantalla",
                "No hay calibración de pantalla guardada. El modo visual mide el "
                "refresco real de tu pantalla para decidir honestamente qué "
                "ritmos puede emitir.\n\n¿Calibrar ahora? (~2 s a pantalla "
                "completa)"):
            run_screen_calibration()
    try:
        req, cap = compute_visual_capability()
    except (ValueError, TypeError) as e:
        messagebox.showerror("Modo visual", str(e))
        return
    if not cap.available:
        refresh = get_visual_refresh_hz()
        substitute = visual.best_substitute(refresh)
        harmonics_on = get_visual_settings()["harmonics_enabled"]
        harmonic = (visual.harmonic_candidate(req["rate_hz"], refresh)
                    if harmonics_on else None)
        msg = (
            f"El ritmo pedido ({req['rate_hz']:.2f} Hz) no se puede emitir en "
            f"esta pantalla.\n\nRazón: {cap.reason}\n\n"
            f"Alternativa: usar el ritmo exacto más alto que soporta tu "
            f"pantalla, {substitute.effective_hz:.2f} Hz - una frecuencia "
            f"DISTINTA a la pedida.")
        if harmonic is not None:
            msg += (f"\n\nExperimental: armónico ~{harmonic.harmonic_of_hz:.2f} Hz "
                    f"(pulsos a {harmonic.effective_hz:.2f} Hz, potencia menor).")
            reply = messagebox.askyesnocancel(
                "Modo visual no disponible",
                msg + "\n\n[Sí] sustituto - [No] armónico - [Cancelar] no iniciar")
            if reply is None:
                return
            cap = substitute if reply else harmonic
        else:
            if not messagebox.askyesno("Modo visual no disponible", msg):
                return
            cap = substitute
    start_visual_mode(cap, req)


def run_screen_calibration():
    """Mide el refresco real de la pantalla (~2 s a pantalla completa).

    Alterna fotogramas cronometrando cada presentacion con perf_counter;
    persiste refresh (mediana) y jitter (p95) en ~/.neuralbeat/config.json.
    """
    stamps = []
    cal_win = None
    try:
        cal_win = tk.Toplevel(root)
        cal_win.attributes("-fullscreen", True)
        cal_win.configure(bg="#000000")
        cal_canvas = tk.Canvas(cal_win, bg="#000000", highlightthickness=0)
        cal_canvas.pack(fill=tk.BOTH, expand=True)
        cal_rect = cal_canvas.create_rectangle(
            0, 0, cal_win.winfo_screenwidth(),
            cal_win.winfo_screenheight(),
            fill="#000000", outline="")
        cal_win.focus_force()
        try:
            cal_win.update_idletasks()
            cal_win.update()
        except Exception:
            pass
        colors = ("#FFFFFF", "#000000")
        t_end = time.perf_counter() + 2.0
        i = 0
        while time.perf_counter() < t_end:
            cal_canvas.itemconfig(cal_rect, fill=colors[i % 2])
            cal_win.update()
            stamps.append(time.perf_counter())
            i += 1
    except Exception:
        logger.error("Screen calibration failed", exc_info=True)
    finally:
        if cal_win is not None:
            try:
                cal_win.destroy()
            except Exception:
                pass
    try:
        refresh, jitter = visual.compute_refresh_stats(stamps)
        ok, confidence = visual.validate_refresh_measurement(refresh, jitter)
        v = config.get("visual") if isinstance(config.get("visual"), dict) else {}
        if ok:
            v["refresh_hz"] = refresh
            v["confidence"] = confidence
            detail = (f"Refresco medido: {refresh:.1f} Hz "
                      f"(jitter p95 {jitter:.2f} ms, confianza {confidence}).")
        else:
            # Medición no plausible (sesión remota, compositor sin límite de
            # fotogramas...): refresco nominal del sistema si existe; si no,
            # default conservador e invitación a recalibrar.
            sys_hz = probe_system_refresh_hz()
            if sys_hz:
                v["refresh_hz"] = sys_hz
                v["confidence"] = "sistema"
                detail = (f"Medición no fiable ({refresh:.0f} Hz, jitter "
                          f"{jitter:.1f} ms). Se usa el refresco que reporta el "
                          f"sistema: {sys_hz:.2f} Hz (no medido). Prueba "
                          f"'Recalibrar pantalla' en un escritorio real.")
            else:
                v["refresh_hz"] = visual.DEFAULT_REFRESH_HZ
                v["confidence"] = "baja"
                detail = (f"Medición no fiable ({refresh:.0f} Hz, jitter "
                          f"{jitter:.1f} ms). Se usa {visual.DEFAULT_REFRESH_HZ:.0f} Hz "
                          f"por defecto y el gate queda conservador. Prueba "
                          f"'Recalibrar pantalla' en un escritorio real.")
        v["jitter_ms"] = jitter
        v["calibrated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        config["visual"] = v
        save_config(config)
        messagebox.showinfo("Calibración de pantalla", detail)
        logger.info("Screen calibration: %s", detail)
    except (ValueError, ZeroDivisionError) as e:
        messagebox.showerror("Calibración de pantalla",
                             f"No se pudo medir el refresco: {e}")
    update_visual_button()


def start_visual_mode(cap, req):
    """Abre el estroboscopio a pantalla completa anclado al audio que suena."""
    global visual_mode_active, visual_window, visual_scheduler
    global visual_lateness_monitor, visual_active_cap, visual_active_gen
    global visual_active_req, visual_beat_clock, visual_active_status

    settings = get_visual_settings()
    off_color, on_color = visual.INTENSITY_PAIRS.get(
        settings["intensity"], visual.INTENSITY_PAIRS["comoda"])
    refresh = get_visual_refresh_hz()

    gen = audio_engine.generator
    cfg = audio_engine.current_config
    if gen is None or cfg is None:
        messagebox.showerror("Modo visual", "No hay audio activo.")
        return

    if req["mode"] == "ramp" and req["ramp_s"]:
        beat_clock = visual.BeatClock(start_hz=max(0.1, req["start_hz"]),
                                      end_hz=max(0.1, req["end_hz"]),
                                      ramp_s=req["ramp_s"])
    else:
        beat_clock = visual.BeatClock(rate_hz=max(0.1, req["rate_hz"]))

    strobe_win = tk.Toplevel(root)
    strobe_win.attributes("-fullscreen", True)
    strobe_win.configure(bg=off_color)
    strobe_canvas = tk.Canvas(strobe_win, bg=off_color, highlightthickness=0)
    strobe_canvas.pack(fill=tk.BOTH, expand=True)
    strobe_rect = strobe_canvas.create_rectangle(
        0, 0, 4000, 4000, fill=off_color, outline="")

    def _on_strobe_resize(event):
        try:
            strobe_canvas.coords(strobe_rect, 0, 0, event.width, event.height)
        except Exception:
            pass

    strobe_canvas.bind("<Configure>", _on_strobe_resize)

    def _on_flip(state):
        try:
            strobe_canvas.itemconfig(strobe_rect,
                                     fill=on_color if state else off_color)
        except Exception:
            pass

    def _rebuild(rate_hz):
        # Rampas: el patron sigue el valor del barrido en curso
        if req["mode"] != "ramp":
            return None
        try:
            cap_now = visual.visual_capability(
                rate_hz, refresh, get_visual_settings()["harmonics_enabled"])
        except Exception:
            return None
        if not cap_now.available:
            return None  # el gate ya valido el barrido; se mantiene el patron
        return (cap_now.pattern, cap_now.cycles_per_window)

    scheduler = visual.StrobeScheduler(
        cap.pattern, refresh, _on_flip,
        clock=time.perf_counter,
        get_audio_time=get_visual_audio_time,
        beat_clock=beat_clock,
        cycles_per_window=cap.cycles_per_window,
        free_running=(cap.state == "armonico"),
        reanchor_interval_s=1.0,
        rebuild_fn=_rebuild)

    # Salida inmediata: cualquier tecla o clic cierra y restaura la ventana
    for btn in (1, 2, 3):
        strobe_win.bind(f"<Button-{btn}>", lambda e: close_visual_mode())
    strobe_win.bind("<Key>", lambda e: close_visual_mode())
    strobe_win.protocol("WM_DELETE_WINDOW", lambda: close_visual_mode())
    try:
        strobe_win.focus_force()
    except Exception:
        pass

    visual_window = strobe_win
    visual_scheduler = scheduler
    visual_lateness_monitor = visual.LatenessMonitor(1.0 / refresh)
    visual_active_cap = cap
    visual_active_gen = gen
    visual_active_req = req
    visual_beat_clock = beat_clock
    visual_mode_active = True

    base_label = visual.capability_label(
        cap, req["rate_hz"] if req["mode"] != "ramp" else None)
    if cap.requested_hz is None and req["rate_hz"]:
        base_label += " (sustituto: frecuencia distinta a la pedida)"
    visual_active_status = (
        f"Visual activo: {base_label} - cierra con cualquier tecla/clic - "
        f"{visual.intensity_note(settings['intensity'])} - "
        f"no es un dispositivo médico ni un tratamiento")
    update_visual_button()
    # start() ancla al pulso de audio y deja started=True: sin el, el primer
    # poll() devuelve None y el modo se cierra al instante ("el audio no avanza").
    scheduler.start()
    visual_poll()


def visual_poll():
    """Bucle Tk del modo visual: flips por deadline, vigilancia de audio y
    abort automatico si la tasa lograda cae por debajo de la requerida."""
    global visual_after_id, visual_active_status, visual_status_last_refresh
    if not visual_mode_active:
        visual_after_id = None
        return
    # El audio se detuvo, termino o cambio de sesion -> cierre inmediato
    gen = visual_active_gen
    if ((not audio_engine.is_playing) or (audio_engine.generator is not gen)
            or gen.is_finished):
        close_visual_mode("el audio se detuvo o terminó")
        return
    sched = visual_scheduler
    if sched is None:
        close_visual_mode()
        return
    now = time.perf_counter()
    next_deadline = sched.poll()
    if next_deadline is None:
        close_visual_mode("el audio no avanza")
        return
    # Abort automatico: mediana de lateness por encima del 15% del fotograma
    lateness = sched.last_flip_lateness
    if lateness is not None and visual_lateness_monitor is not None:
        visual_lateness_monitor.record(now, lateness)
        sched.last_flip_lateness = None
        if visual_lateness_monitor.should_abort():
            close_visual_mode(
                "cerrado: tasa lograda insuficiente (compositor sobrecargado)")
            return
    # Rampa: refrescar el ritmo en curso en la etiqueta (~2 Hz)
    try:
        if (visual_active_req is not None
                and visual_active_req["mode"] == "ramp"
                and visual_beat_clock is not None
                and now - visual_status_last_refresh > 0.5):
            visual_status_last_refresh = now
            cur = visual_beat_clock.rate_at(get_visual_audio_time())
            cap_now = visual.visual_capability(cur, get_visual_refresh_hz())
            visual_active_status = (
                f"Visual activo: rampa en {cur:.2f} Hz - "
                f"{visual.capability_label(cap_now, cur)} - "
                f"cierra con cualquier tecla/clic")
            update_visual_button()
    except Exception:
        logger.debug("Visual status refresh failed", exc_info=True)
    delay_ms = 100.0
    try:
        delay_ms = max(1.0, min(100.0,
                                (next_deadline - time.perf_counter()) * 1000.0 - 1.0))
    except Exception:
        pass
    visual_after_id = root.after(int(delay_ms), visual_poll)


def close_visual_mode(reason=None):
    """Cierra el modo visual y restaura la ventana principal (foco incluido)."""
    global visual_mode_active, visual_window, visual_scheduler, visual_after_id
    global visual_active_gen, visual_active_cap, visual_active_req
    global visual_beat_clock, visual_active_status, visual_last_reason
    if visual_after_id is not None:
        try:
            root.after_cancel(visual_after_id)
        except Exception:
            pass
        visual_after_id = None
    if visual_scheduler is not None:
        visual_scheduler.stop()
        visual_scheduler = None
    if visual_window is not None:
        win = visual_window
        visual_window = None
        try:
            win.destroy()
        except Exception:
            pass
    was_active = visual_mode_active
    visual_mode_active = False
    visual_active_gen = None
    visual_active_cap = None
    visual_active_req = None
    visual_beat_clock = None
    visual_active_status = None
    if reason:
        visual_last_reason = f"modo visual {reason}"
        logger.info("Modo visual: %s", reason)
    if was_active:
        try:
            root.deiconify()
            root.focus_set()
        except Exception:
            pass
    update_visual_button()


def set_visual_intensity():
    """Intensidad cómoda (default) o brillante (opt-in con advertencia)."""
    intensity = visual_intensity_var.get() if visual_intensity_var else "comoda"
    if intensity == "brillante":
        messagebox.showwarning(
            "Intensidad brillante",
            "Has elegido intensidad brillante: el parpadeo usará el contraste "
            "máximo (negro / blanco puro).\n\nEl mayor contraste implica mayor "
            "respuesta visual esperada y una estimulación más intensa. Ante "
            "malestar, cierra con cualquier tecla y vuelve a la intensidad "
            "cómoda.")
    save_visual_setting(
        "intensity", intensity if intensity in visual.INTENSITY_PAIRS else "comoda")
    update_visual_button()


def on_visual_harmonics_toggle():
    """Flag avanzado del modo armónico experimental (apagado por defecto)."""
    enabled = bool(visual_harmonics_var.get()) if visual_harmonics_var else False
    save_visual_setting("harmonics_enabled", enabled)
    if enabled:
        messagebox.showinfo(
            "Modo armónico experimental",
            "Habilitado el modo armónico EXPERIMENTAL.\n\nCuando el ritmo pedido "
            "no esté disponible en tu pantalla, se podrá ofrecer un patrón a un "
            "divisor entero del refresco cuyo 2º armónico aproxime el ritmo "
            "pedido (p. ej. 40 Hz pedidos en una pantalla de ~60 Hz: pulsos de "
            "~19.93 Hz con 2º armónico en ≈39.87 Hz).\n\nEntrega MENOS potencia "
            "que la frecuencia pedida y añade una componente en la frecuencia "
            "fundamental.")
    update_visual_button()


# =============================================================================
# UI & Interaction
# =============================================================================

def set_osc_merge_waves():
    """Saves the merge waves setting and updates the live plot's static elements."""
    if osc_merge_var is None:
        return

    is_merged = osc_merge_var.get()
    config["osc_merge_waves"] = is_merged
    save_config(config)

    # If window is open, update its appearance in real-time
    if osc_window and visualizer_ax and visualizer_canvas:
        try:
            # Update horizontal line visibility
            if hasattr(visualizer_ax, '_hline'):
                visualizer_ax._hline.set_visible(not is_merged)

            # Update Y-ticks
            if is_merged:
                visualizer_ax.set_yticks([-1, 0, 1])
                visualizer_ax.tick_params(axis='y', colors=visualizer_ax.yaxis.label.get_color(), length=4)
            else:
                visualizer_ax.set_yticks([])
                visualizer_ax.tick_params(axis='y', length=0)
            visualizer_canvas.draw_idle()
        except Exception:
            pass # Ignore if widgets are being destroyed

def set_osc_colors(palette_name: str):
    """Sets the oscilloscope color palette and saves to config."""
    if palette_name not in OSC_COLOR_PALETTES:
        return

    config["osc_colors"] = palette_name
    save_config(config)

    # If oscilloscope is open, update its colors in real-time
    if osc_window and visualizer_canvas and line_left and line_right:
        try:
            is_dark = root.style.theme_use() in ["darkly", "superhero"]
            theme_mode = "dark" if is_dark else "light"

            colors = OSC_COLOR_PALETTES[palette_name][theme_mode]
            line_left.set_color(colors[0])
            line_right.set_color(colors[1])
            visualizer_canvas.draw_idle()
        except Exception:
            # Ignore errors if window/widgets are in a weird state
            pass

def toggle_oscilloscope_window():
    """Opens or closes the real-time oscilloscope window."""
    global osc_window, visualizer_canvas, visualizer_ax, line_left, line_right
    global osc_plot_buffer_l, osc_plot_buffer_r

    # If window exists, destroy it and clear references
    if osc_window and osc_window.winfo_exists():
        osc_window.destroy()
        osc_window = None
        visualizer_canvas = None
        visualizer_ax = None
        line_left = None
        line_right = None
        osc_plot_buffer_l = None
        osc_plot_buffer_r = None
        return

    # Create new window
    osc_window = tb.Toplevel(root)
    osc_window.title("Real-time Oscilloscope")
    osc_window.geometry("600x300")

    def on_osc_close():
        """Callback for when the oscilloscope window is closed by the user."""
        global osc_window, visualizer_canvas, visualizer_ax, line_left, line_right
        global osc_plot_buffer_l, osc_plot_buffer_r

        win_to_destroy = osc_window

        # Nullify globals to prevent race conditions with the update loop
        osc_window = None
        visualizer_canvas = None
        visualizer_ax = None
        line_left = None
        line_right = None
        osc_plot_buffer_l = None
        osc_plot_buffer_r = None

        # Since we overrode the protocol, we are responsible for destroying the window.
        if win_to_destroy:
            try:
                win_to_destroy.destroy()
            except tk.TclError:
                pass # Window is already being destroyed

    osc_window.protocol("WM_DELETE_WINDOW", on_osc_close)

    # Initialize plot buffers
    sample_rate = 44100  # Match audio engine
    buffer_size = int(OSC_BUFFER_SECONDS * sample_rate)
    osc_plot_buffer_l = np.zeros(buffer_size, dtype=np.float32)
    osc_plot_buffer_r = np.zeros(buffer_size, dtype=np.float32)

    fig = Figure(figsize=(5, 2), dpi=100)
    visualizer_ax = fig.add_subplot(111)

    # Style the plot to match the theme
    is_dark = root.style.theme_use() in ["darkly", "superhero"]
    theme_mode = "dark" if is_dark else "light"

    current_palette_name = config.get("osc_colors", "Cyan / Magenta")
    palette = OSC_COLOR_PALETTES.get(current_palette_name, OSC_COLOR_PALETTES["Cyan / Magenta"])
    colors = palette[theme_mode]
    line_color_l, line_color_r = colors

    bg_color = root.style.colors.get("bg")
    fg_color = root.style.colors.get("fg")

    fig.patch.set_facecolor(bg_color)
    visualizer_ax.set_facecolor(bg_color)
    visualizer_ax.tick_params(axis='both', colors=fg_color, length=0)
    visualizer_ax.spines['bottom'].set_color(fg_color)
    visualizer_ax.spines['top'].set_color(fg_color)
    visualizer_ax.spines['left'].set_color(fg_color)
    visualizer_ax.spines['right'].set_color(fg_color)
    visualizer_ax.xaxis.label.set_color(fg_color)
    visualizer_ax.yaxis.label.set_color(fg_color)

    # Add a horizontal line to separate channels, and store a reference to it
    visualizer_ax._hline = visualizer_ax.axhline(0, color=fg_color, lw=0.5, ls='--')

    x_data = np.arange(buffer_size)
    line_left, = visualizer_ax.plot(x_data, osc_plot_buffer_l, lw=1, color=line_color_l)
    line_right, = visualizer_ax.plot(x_data, osc_plot_buffer_r, lw=1, color=line_color_r)

    visualizer_ax.set_ylim(-1.1, 1.1)
    visualizer_ax.set_xlim(0, buffer_size)
    visualizer_ax.set_xticks([])

    # Set initial view based on config
    is_merged = config.get("osc_merge_waves", False)
    visualizer_ax._hline.set_visible(not is_merged)
    if is_merged:
        visualizer_ax.set_yticks([-1, 0, 1])
        visualizer_ax.tick_params(axis='y', colors=fg_color, length=4)
    else:
        visualizer_ax.set_yticks([])
        visualizer_ax.tick_params(axis='y', length=0)

    fig.tight_layout()

    visualizer_canvas = FigureCanvasTkAgg(fig, master=osc_window)
    visualizer_canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

def _run_export_thread(cfg, filename, duration, progress_win, progress_bar, progress_label, on_success, on_error):
    """Background thread function for exporting audio to a WAV file."""
    try:
        sample_rate = cfg.sample_rate
        total_frames = int(duration * sample_rate)
        block_size = 4096

        generator = BinauralGenerator(cfg)

        frames_written = 0
        all_audio = []

        while frames_written < total_frames:
            # Check for window close (cancellation) via event or shared flag?
            # For simplicity, we just check if window exists via main thread callback

            chunk_size = min(block_size, total_frames - frames_written)
            audio_block = generator.generate_block(chunk_size)
            all_audio.append(audio_block)
            frames_written += chunk_size

            percent = (frames_written / total_frames) * 100

            def update_ui(p=percent):
                try:
                    if progress_win.winfo_exists():
                        progress_bar['value'] = p
                        progress_label.config(text=f"Generating... {int(p)}%")
                except Exception: pass

            root.after(0, update_ui)

        full_audio = np.concatenate(all_audio)

        # Apply fade out to the very end (last 20ms) for clean cut
        fade_len = int(0.02 * sample_rate)
        if len(full_audio) > fade_len:
            ramp = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
            full_audio[-fade_len:] *= ramp[:, np.newaxis]

        wavfile.write(filename, sample_rate, full_audio)

        root.after(0, lambda: on_success(filename))

    except Exception as e:
        root.after(0, lambda: on_error(e))

def export_audio_file():
    """Initiates the audio export process with UI dialogs."""
    stop_audio()

    try:
        cfg = get_audio_config_from_ui()
        default_duration = cfg.ramp_duration_s if cfg.use_ramp else 300.0

        duration_str = simpledialog.askstring("Export Audio", f"Enter duration in seconds:", initialvalue=str(int(default_duration)))
        if not duration_str:
            return

        try:
            duration = float(duration_str)
            if duration <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Input Error", "Duration must be a positive number.")
            return

        filename = filedialog.asksaveasfilename(
            title="Export WAV",
            defaultextension=".wav",
            filetypes=[("WAV files", "*.wav")]
        )
        if not filename:
            return

        # Progress Window
        progress_win = tb.Toplevel(root)
        progress_win.title("Exporting...")
        progress_win.geometry("300x100")

        progress_label = ttk.Label(progress_win, text="Generating audio...")
        progress_label.pack(pady=10)
        progress_bar = ttk.Progressbar(progress_win, mode='determinate')
        progress_bar.pack(fill=tk.X, padx=20, pady=10)

        def on_success(fname):
            try:
                if progress_win.winfo_exists():
                    progress_win.destroy()
                logger.info(f"Exported audio to {fname}")
                messagebox.showinfo("Export Complete", f"Saved to {fname}")
            except Exception: pass

        def on_error(e):
            try:
                if progress_win.winfo_exists():
                    progress_win.destroy()
                logger.error("Export failed", exc_info=True)
                messagebox.showerror("Export Error", f"Export failed: {str(e)}")
            except Exception: pass

        t = threading.Thread(target=_run_export_thread, args=(cfg, filename, duration, progress_win, progress_bar, progress_label, on_success, on_error))
        t.start()

    except ValueError as e:
        messagebox.showerror("Input Error", str(e))
    except Exception as e:
        logger.error("Export initialization failed", exc_info=True)
        messagebox.showerror("Export Error", str(e))

def play_audio():
    """Starts audio playback based on current UI settings."""
    global play_mode
    global ramp_carrier_hz, ramp_start_beat_hz, ramp_end_beat_hz, ramp_duration_s
    global manual_left_hz, manual_right_hz
    global live_status_after_id

    try:
        cfg = get_audio_config_from_ui()

        if cfg.use_ramp:
            play_mode = "ramp"
            ramp_carrier_hz = cfg.carrier_hz
            ramp_start_beat_hz = cfg.start_beat_hz
            ramp_end_beat_hz = cfg.end_beat_hz
            ramp_duration_s = cfg.ramp_duration_s

            beat_now = ramp_start_beat_hz
            left_frequency_entry.delete(0, tk.END)
            right_frequency_entry.delete(0, tk.END)
            left_frequency_entry.insert(0, str(ramp_carrier_hz - beat_now / 2.0))
            right_frequency_entry.insert(0, str(ramp_carrier_hz + beat_now / 2.0))
        else:
            play_mode = "manual"
            manual_left_hz = cfg.left_frequency
            manual_right_hz = cfg.right_frequency

        audio_engine.start(cfg)

        if live_status_after_id is None:
            update_live_status()

        # El gate visual puede cambiar (modo rampa reescribe las entradas)
        update_visual_button()
    except ValueError as e:
         messagebox.showerror("Input Error", str(e))
    except Exception as e:
        logger.error("Error playing audio", exc_info=True)
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")

def show_about():
    about_text = """
NeuralBeat 1.0.0 - maintained fork by MoriNo23
https://github.com/MoriNo23/NeuralBeat

Based on the original NeuralBeat by Ægean (2023-2026):
https://github.com/Aegean-E/NeuralBeat
Twitter: twitter.com/@Aegean_E

Licensed under the Apache License Version 2.0, January 2004.
    """
    messagebox.showinfo("About", about_text)

def set_theme(theme_name: str):
    try:
        root.style.theme_use(theme_name)
        config["theme"] = theme_name
        save_config(config)
    except Exception as e:
        messagebox.showerror("Theme Error", str(e))

def export_config_json():
    """Export the current in-memory config dict to a JSON file the user selects."""
    try:
        out_path = filedialog.asksaveasfilename(
            title="Export config.json",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
            initialfile="config.json",
        )
        if not out_path:
            return

        Path(out_path).write_text(json.dumps(dict(config), indent=2), encoding="utf-8")
        messagebox.showinfo("Export", f"Exported configuration to:\n{out_path}")
    except Exception as e:
        messagebox.showerror("Export Error", str(e))

def import_config_json():
    """Import config from a JSON file, persist it, and refresh UI (theme + presets)."""
    global config

    try:
        in_path = filedialog.askopenfilename(
            title="Import config.json",
            filetypes=[("JSON files", "*.json")],
        )
        if not in_path:
            return

        imported = json.loads(Path(in_path).read_text(encoding="utf-8"))
        if not isinstance(imported, dict):
            raise ValueError("Invalid config file: root JSON value must be an object.")

        # Normalize user_presets shape so preset UI won't crash
        up = imported.get("user_presets", {})
        if not isinstance(up, dict):
            up = {}

        def _validate_presets(presets_list):
            valid_presets = []
            if not isinstance(presets_list, list):
                return []
            for p in presets_list:
                if isinstance(p, dict) and "label" in p and "left_hz" in p and "right_hz" in p:
                    if not isinstance(p["label"], str):
                        continue
                    try:
                        p["left_hz"] = float(p["left_hz"])
                        p["right_hz"] = float(p["right_hz"])
                        valid_presets.append(p)
                    except (ValueError, TypeError):
                        continue
            return valid_presets

        new_config = {
            "user_presets": {
                "Monaural": _validate_presets(up.get("Monaural")),
                "Binaural": _validate_presets(up.get("Binaural")),
            }
        }

        if "theme" in imported:
            new_config["theme"] = imported["theme"]

        config = new_config
        save_config(config)

        # Apply theme if available
        theme = config.get("theme")
        if isinstance(theme, str) and theme.strip():
            try:
                root.style.theme_use(theme.strip())
            except Exception:
                pass

        # Rebuild preset buttons to reflect imported presets
        build_preset_buttons()

        messagebox.showinfo("Import", f"Imported configuration from:\n{in_path}")
    except Exception as e:
        logger.error("Error importing config", exc_info=True)
        messagebox.showerror("Import Error", str(e))

def apply_preset(left_hz: float = 0, right_hz: float = 0, category: str = "Binaural", carrier_hz: float = None, pulse_hz: float = None):
    if category == "Isochronic" and carrier_hz is not None and pulse_hz is not None:
        left_frequency_entry.delete(0, tk.END)
        right_frequency_entry.delete(0, tk.END)
        left_frequency_entry.insert(0, str(pulse_hz))
        right_frequency_entry.insert(0, str(carrier_hz))
        
        if beat_type_var:
            beat_type_var.set("isochronic")
        if carrier_entry:
            carrier_entry.delete(0, tk.END)
            carrier_entry.insert(0, str(carrier_hz))
    else:
        left_frequency_entry.delete(0, tk.END)
        right_frequency_entry.delete(0, tk.END)
        left_frequency_entry.insert(0, str(left_hz))
        right_frequency_entry.insert(0, str(right_hz))
        if beat_type_var:
            beat_type_var.set("binaural")

    # El estado del gate visual depende del ritmo activo
    update_visual_button()

def build_preset_buttons():
    allp = get_all_presets()
    
    # Clear frames
    for w in binaural_monaural_frame.winfo_children():
        w.destroy()
    for w in isochronic_beats_frame.winfo_children():
        w.destroy()

    # Combined Binaural + Monaural presets
    combined_presets = allp["Binaural"] + allp["Monaural"]
    for i, p in enumerate(combined_presets):
        btn = ttk.Button(
            binaural_monaural_frame,
            text=p["label"],
            command=lambda l=p["left_hz"], r=p["right_hz"], c="Binaural": apply_preset(l, r, c)
        )
        btn.grid(row=i, column=0, padx=10, pady=3, sticky="ew")

    # Isochronic presets - use carrier_hz and pulse_hz
    for i, p in enumerate(allp["Isochronic"]):
        carrier = p.get("carrier_hz", 200.0)
        pulse = p.get("pulse_hz", 10.0)
        btn = ttk.Button(
            isochronic_beats_frame,
            text=p["label"],
            command=lambda c=carrier, pl=pulse: apply_preset(0, 0, "Isochronic", carrier_hz=c, pulse_hz=pl)
        )
        btn.grid(row=i, column=0, padx=10, pady=3, sticky="ew")

def save_current_as_preset():
    try:
        name = preset_name_entry.get().strip()
        try:
            left_hz = float(left_frequency_entry.get())
            right_hz = float(right_frequency_entry.get())
        except ValueError:
            messagebox.showerror("Input Error", "Invalid frequency values.")
            return

        err = validate_audio_params(left_hz, right_hz, 50, 50) # Volume doesn't matter for preset, passing dummy
        if err:
             # Strip "Volume..." errors if any (unlikely with dummy) or just show generic if freq error
             if "Frequency" in err:
                 messagebox.showerror("Input Error", err)
                 return

        category = preset_category_var.get().strip()
        if not category:
            category = "Binaural" if abs(right_hz - left_hz) > 0 else "Monaural"

        add_user_preset(category=category, label=name, left_hz=left_hz, right_hz=right_hz)

        preset_name_entry.delete(0, tk.END)
        build_preset_buttons()
        messagebox.showinfo("Preset Saved", f"Saved preset '{name}'")
    except Exception as e:
        logger.error("Error saving preset", exc_info=True)
        messagebox.showerror("Preset Error", str(e))

def delete_preset():
    try:
        category = preset_category_var.get().strip()
        label = preset_name_entry.get().strip()
        if not label:
            raise ValueError("Enter the preset name to remove (must match exactly).")

        if messagebox.askyesno("Remove Preset", f"Remove user preset '{label}' from {category}?"):
            removed = remove_user_preset(category=category, label=label)
            if removed:
                build_preset_buttons()
                messagebox.showinfo("Preset Removed", f"Removed preset '{label}'")
            else:
                messagebox.showwarning("Not Found", f"No user preset named '{label}' found in {category}.")
    except Exception as e:
        messagebox.showerror("Remove Preset Error", str(e))

def update_live_status():
    """Updates the status bar with current frequencies and remaining time."""
    global live_status_after_id
    global osc_merge_var
    global osc_plot_buffer_l, osc_plot_buffer_r

    # If window is gone, do not reschedule
    try:
        if not root.winfo_exists():
            live_status_after_id = None
            return
    except Exception:
        live_status_after_id = None
        return

    if audio_engine.is_playing:
        elapsed = audio_engine.get_elapsed_time()

        if play_mode == "ramp":
            beat = _compute_ramped_beat_hz(elapsed, ramp_start_beat_hz, ramp_end_beat_hz, ramp_duration_s)
            lf = ramp_carrier_hz - (beat / 2.0)
            rf = ramp_carrier_hz + (beat / 2.0)

            remaining_s = max(0.0, ramp_duration_s - elapsed)
            rem_m = int(remaining_s // 60)
            rem_s = int(remaining_s % 60)

            current_beat_type = beat_type_var.get() if beat_type_var else "binaural"
            if current_beat_type == "isochronic":
                status_var.set(
                    f"Isochronic: {beat:.2f} Hz Beat | Carrier: {ramp_carrier_hz:.2f} Hz | Remaining: {rem_m:02d}:{rem_s:02d}"
                )
            else:
                status_var.set(
                    f"Beat: {beat:.2f} Hz | L: {lf:.2f} Hz | R: {rf:.2f} Hz | Remaining: {rem_m:02d}:{rem_s:02d}"
                )
        else:
            beat = abs(manual_right_hz - manual_left_hz)
            current_beat_type = beat_type_var.get() if beat_type_var else "binaural"
            if current_beat_type == "isochronic":
                status_var.set(f"Isochronic: {manual_left_hz:.2f} Hz Beat | Carrier: {manual_right_hz:.2f} Hz")
            else:
                status_var.set(f"Beat: {beat:.2f} Hz | L: {manual_left_hz:.2f} Hz | R: {manual_right_hz:.2f} Hz")
    else:
        status_var.set("Beat: — Hz | L: — Hz | R: — Hz")

    # Update Oscilloscope
    if visualizer_canvas:
        try:
            is_merged = config.get("osc_merge_waves", False)
            block = audio_engine.get_last_block()
            if block is not None and len(block) > 0 and osc_plot_buffer_l is not None:
                n_frames = len(block)

                # Roll the buffers and append new data
                osc_plot_buffer_l = np.roll(osc_plot_buffer_l, -n_frames)
                osc_plot_buffer_r = np.roll(osc_plot_buffer_r, -n_frames)
                osc_plot_buffer_l[-n_frames:] = block[:, 0]
                osc_plot_buffer_r[-n_frames:] = block[:, 1]

                # Update the plot data
                if is_merged:
                    line_left.set_ydata(osc_plot_buffer_l)
                    line_right.set_ydata(osc_plot_buffer_r)
                else:
                    line_left.set_ydata(0.5 + osc_plot_buffer_l * 0.5)
                    line_right.set_ydata(-0.5 + osc_plot_buffer_r * 0.5)
                visualizer_canvas.draw_idle()

            elif not audio_engine.is_playing:
                # Clear the buffers and the plot when stopped
                if osc_plot_buffer_l is not None and np.any(osc_plot_buffer_l):
                    osc_plot_buffer_l.fill(0)
                    osc_plot_buffer_r.fill(0)
                    if is_merged:
                        line_left.set_ydata(osc_plot_buffer_l)
                        line_right.set_ydata(osc_plot_buffer_r)
                    else:
                        line_left.set_ydata(0.5 + osc_plot_buffer_l * 0.5)
                        line_right.set_ydata(-0.5 + osc_plot_buffer_r * 0.5)
                    visualizer_canvas.draw_idle()
        except Exception:
            # Window might have been closed during update. Ignore.
            pass

    live_status_after_id = root.after(50, update_live_status)

def on_close():
    try:
        if visual_mode_active:
            close_visual_mode()
        stop_audio()
    finally:
        try:
            root.destroy()
        except Exception:
            logger.error("Error closing application", exc_info=True)

def create_frequency_control_frame(parent, title, column, waveform_options, default_freq="432", default_vol="50", default_waveform="Sine"):
    frame = ttk.LabelFrame(parent, text=title)
    frame.grid(row=0, column=column, padx=10, pady=8, sticky="nsew")

    freq_label = ttk.Label(frame, text="Frequency (Hz):")
    freq_label.grid(row=0, column=0, padx=10, pady=5)
    freq_entry = ttk.Entry(frame)
    freq_entry.grid(row=0, column=1, padx=10, pady=5)
    freq_entry.insert(0, default_freq)

    vol_label = ttk.Label(frame, text="Volume (%):")
    vol_label.grid(row=1, column=0, padx=10, pady=5)
    vol_entry = ttk.Entry(frame)
    vol_entry.grid(row=1, column=1, padx=10, pady=5)
    vol_entry.insert(0, default_vol)

    waveform_label = ttk.Label(frame, text="Waveform:")
    waveform_label.grid(row=2, column=0, padx=10, pady=5)
    waveform_var = tk.StringVar()
    waveform_combobox = ttk.Combobox(
        frame,
        textvariable=waveform_var,
        values=waveform_options
    )
    waveform_combobox.grid(row=2, column=1, padx=10, pady=5)
    waveform_combobox.set(default_waveform)

    return freq_entry, vol_entry, waveform_var, waveform_combobox, freq_label, vol_label, waveform_label, frame

def main():
    """Main application entry point. Initializes UI and starts the event loop."""
    global root
    global left_frequency_entry, left_volume_entry, left_waveform_var, left_waveform_combobox
    global right_frequency_entry, right_volume_entry, right_waveform_var, right_waveform_combobox
    global monaural_beats_frame, binaural_beats_frame, isochronic_beats_frame, binaural_monaural_frame
    global preset_name_entry, preset_category_var
    global carrier_entry, start_beat_entry, end_beat_entry, ramp_minutes_entry, noise_type_var, noise_volume_entry
    global status_var, ramp_enabled_var, osc_merge_var, beat_type_var
    global visual_toggle_button, visual_status_label, visual_intensity_var
    global visual_harmonics_var

    import sys
    if "--debug" in sys.argv:
        print("========================================")
        print("SCIENTIFIC VERIFICATION & DEBUG REPORT")
        print("========================================")
        try:
            # Generate a test signal: 432 Hz Carrier, 10 Hz Beat (Alpha)
            print("[INFO] Generating 1s test signal (432Hz Carrier, 10Hz Beat)...")
            test_cfg = AudioConfig(
                sample_rate=44100,
                left_volume=0.8,
                right_volume=0.8,
                noise_type="None",
                noise_volume=0.0,
                left_waveform="Sine",
                right_waveform="Sine",
                use_ramp=False,
                left_frequency=427.0, # 432 - 5
                right_frequency=437.0, # 432 + 5
                carrier_hz=0.0,
                start_beat_hz=0.0,
                end_beat_hz=0.0,
                ramp_duration_s=0.0
            )

            gen = BinauralGenerator(test_cfg)
            audio = gen.generate_block(44100)

            print(f"[INFO] Signal generated. Shape: {audio.shape}, Type: {audio.dtype}")
            print(f"[METRICS] Base Freq: 432 Hz")
            print(f"[METRICS] Target Beat: 10 Hz")
            print(f"[METRICS] Total Samples: {len(audio)}")

            # Run Validation
            print("[INFO] Running Signal Validation...")
            errors = verification.validate_signal(audio, 44100, 427.0, 437.0, 1.0)

            if errors:
                print("[FAIL] Signal Verification Failed:")
                for e in errors:
                    print(f"  - {e}")
            else:
                print("[PASS] Signal Verification Passed.")
                print("  - Frequency Accuracy: OK")
                print("  - Amplitude Safety: OK")
                print("  - DC Offset: OK")
                print("  - Stereo Separation: OK")

            # Run Export Validation
            print("\n[INFO] Running Export Validation...")
            exp_errors = verification.validate_export(BinauralGenerator, test_cfg, 1.0)
            if exp_errors:
                print("[FAIL] Export Verification Failed:")
                for e in exp_errors:
                    print(f"  - {e}")
            else:
                print("[PASS] Export Verification Passed.")

        except Exception as e:
            print(f"[ERROR] Debug execution failed: {e}")
            import traceback
            traceback.print_exc()

        print("========================================")
        # Continue to app or exit?
        # Usually debug report prints and exits or prints and continues.
        # If the user just wants the report, they might prefer exit.
        # But if they use --debug to debug the running app, they want it to run.
        # I'll let it run.

    root = tb.Window(themename=initial_theme)
    root.title("NeuralBeat 1.0.0 (fork MoriNo23)")
    
    # Set window icon
    try:
        if os.path.exists("icon.ico"):
            root.iconbitmap("icon.ico")
    except Exception:
        pass
    
    root.protocol("WM_DELETE_WINDOW", on_close)

    osc_merge_var = tk.BooleanVar(value=config.get("osc_merge_waves", False))
    status_var = tk.StringVar(value="Beat: — Hz | L: — Hz | R: — Hz")

    menu_bar = tk.Menu(root)
    root.config(menu=menu_bar)

    settings_menu = tk.Menu(menu_bar, tearoff=False)
    menu_bar.add_cascade(label="Settings", menu=settings_menu)
    settings_menu.add_command(label="About", command=show_about)

    user_profile_menu = tk.Menu(settings_menu, tearoff=False)
    settings_menu.add_cascade(label="User Profile", menu=user_profile_menu)
    user_profile_menu.add_command(label="Import User Profile", command=import_config_json)
    user_profile_menu.add_command(label="Export User Profile", command=export_config_json)

    theme_menu = tk.Menu(settings_menu, tearoff=False)
    settings_menu.add_cascade(label="Theme", menu=theme_menu)
    theme_menu.add_command(label="Dark (Darkly)", command=lambda: set_theme("darkly"))
    theme_menu.add_command(label="Dark (Superhero)", command=lambda: set_theme("superhero"))
    theme_menu.add_command(label="Light (Flatly)", command=lambda: set_theme("flatly"))

    settings_menu.add_separator()

    osc_menu = tk.Menu(settings_menu, tearoff=False)
    settings_menu.add_cascade(label="Oscilloscope", menu=osc_menu)
    osc_menu.add_command(label="Show/Hide Window", command=toggle_oscilloscope_window)
    osc_menu.add_separator()
    color_menu = tk.Menu(osc_menu, tearoff=False)
    osc_menu.add_cascade(label="Line Colors", menu=color_menu)
    for name in OSC_COLOR_PALETTES:
        color_menu.add_command(label=name, command=lambda n=name: set_osc_colors(n))

    osc_menu.add_separator()
    osc_menu.add_checkbutton(label="Merge Waves", variable=osc_merge_var, command=set_osc_merge_waves)

    # --- Visual strobe mode (openspec: estimulacion-visual) ---
    visual_settings_menu = tk.Menu(settings_menu, tearoff=False)
    settings_menu.add_cascade(label="Visual", menu=visual_settings_menu)
    visual_settings_menu.add_command(label="Recalibrar pantalla",
                                      command=run_screen_calibration)
    visual_settings_menu.add_separator()
    visual_intensity_var = tk.StringVar(value=get_visual_settings()["intensity"])
    visual_settings_menu.add_radiobutton(
        label="Intensidad: Cómoda (por defecto)",
        variable=visual_intensity_var, value="comoda",
        command=set_visual_intensity)
    visual_settings_menu.add_radiobutton(
        label="Intensidad: Brillante",
        variable=visual_intensity_var, value="brillante",
        command=set_visual_intensity)
    visual_settings_menu.add_separator()
    visual_harmonics_var = tk.BooleanVar(
        value=get_visual_settings()["harmonics_enabled"])
    visual_settings_menu.add_checkbutton(
        label="Modo armónico experimental (avanzado)",
        variable=visual_harmonics_var, command=on_visual_harmonics_toggle)

    beat_type_var = tk.StringVar(value="binaural")

    left_frequency_entry, left_volume_entry, left_waveform_var, left_waveform_combobox, left_freq_label, left_vol_label, left_waveform_lbl, left_freq_frame = create_frequency_control_frame(
        root, "Left Ear Frequency", 0, list(waveforms.keys()), default_freq="432", default_vol="50", default_waveform="Sine"
    )

    right_frequency_entry, right_volume_entry, right_waveform_var, right_waveform_combobox, right_freq_label, right_vol_label, right_waveform_lbl, right_freq_frame = create_frequency_control_frame(
        root, "Right Ear Frequency", 1, list(waveforms.keys()), default_freq="432", default_vol="50", default_waveform="Sine"
    )

    def update_freq_labels(*args):
        bt = beat_type_var.get() if beat_type_var else "binaural"
        if bt == "isochronic":
            left_freq_label.config(text="Pulse Rate (Hz):")
            right_freq_label.config(text="Carrier Tone (Hz):")
            left_freq_frame.config(text="Isochronic Tone Settings")
            right_freq_frame.config(text="Isochronic Tone Settings")
        else:
            left_freq_label.config(text="Frequency (Hz):")
            right_freq_label.config(text="Frequency (Hz):")
            left_freq_frame.config(text="Left Ear Frequency")
            right_freq_frame.config(text="Right Ear Frequency")

    beat_type_var.trace_add("write", update_freq_labels)
    update_freq_labels()

    # Presets UI (built-in presets.py + user presets from config.json)
    presets_frame = ttk.LabelFrame(root, text="Presets")
    presets_frame.grid(row=0, column=2, rowspan=3, padx=10, pady=8, sticky="nsew")
    presets_frame.columnconfigure(0, weight=1)
    presets_frame.columnconfigure(1, weight=1)
    presets_frame.rowconfigure(0, weight=1)
    presets_frame.rowconfigure(1, weight=0)

    binaural_monaural_frame = ttk.LabelFrame(presets_frame, text="Binaural Beat / Monaural Beat")
    binaural_monaural_frame.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

    isochronic_beats_frame = ttk.LabelFrame(presets_frame, text="Isochronic Tone")
    isochronic_beats_frame.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

    create_preset_frame = ttk.LabelFrame(presets_frame, text="Create / Remove Preset (User Presets)")
    create_preset_frame.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="nsew")

    preset_name_label = ttk.Label(create_preset_frame, text="Name (Exact):")
    preset_name_label.grid(row=0, column=0, padx=10, pady=4, sticky="e")
    preset_name_entry = ttk.Entry(create_preset_frame, width=28)
    preset_name_entry.grid(row=0, column=1, padx=10, pady=4, sticky="w")

    preset_category_label = ttk.Label(create_preset_frame, text="Type:")
    preset_category_label.grid(row=1, column=0, padx=10, pady=4, sticky="e")
    preset_category_var = tk.StringVar(value="Binaural Beat / Monaural Beat")
    preset_category_combo = ttk.Combobox(
        create_preset_frame,
        textvariable=preset_category_var,
        values=["Binaural Beat / Monaural Beat", "Isochronic Tone"],
        state="readonly",
        width=25
    )
    preset_category_combo.grid(row=1, column=1, padx=10, pady=4, sticky="w")

    save_preset_button = ttk.Button(create_preset_frame, text="Save Current Frequencies as Preset", command=save_current_as_preset)
    save_preset_button.grid(row=2, column=0, padx=10, pady=5, sticky="ew")

    delete_preset_button = ttk.Button(create_preset_frame, text="Remove Preset", command=delete_preset)
    delete_preset_button.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

    build_preset_buttons()

    # Ramp controls (under frequency frames)
    advanced_controls_frame = ttk.LabelFrame(root, text="Advanced Controls")
    advanced_controls_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=8, sticky="nsew")

    # Configure grid to center content
    advanced_controls_frame.columnconfigure(0, weight=1)
    advanced_controls_frame.columnconfigure(1, weight=0)
    advanced_controls_frame.columnconfigure(2, weight=1)

    # --- Beat Type selector ---
    beat_type_container = ttk.Frame(advanced_controls_frame)
    beat_type_container.grid(row=0, column=0, columnspan=3, pady=4)
    
    beat_type_subsection = ttk.LabelFrame(beat_type_container, text="Beat Type")
    beat_type_subsection.pack()
    beat_type_subsection.columnconfigure(0, weight=1)
    beat_type_subsection.columnconfigure(1, weight=1)

    ttk.Radiobutton(beat_type_subsection, text="Binaural Beat / Monaural Beat", variable=beat_type_var, value="binaural").grid(row=0, column=0, padx=10, pady=5)
    ttk.Radiobutton(beat_type_subsection, text="Isochronic Tone", variable=beat_type_var, value="isochronic").grid(row=0, column=1, padx=10, pady=5)

    # --- Subsections within the main ramp frame ---
    noise_container = ttk.Frame(advanced_controls_frame)
    noise_container.grid(row=1, column=0, columnspan=3, pady=4)
    noise_subsection_frame = ttk.LabelFrame(noise_container, text="Background Noise")
    noise_subsection_frame.pack()

    ramp_container = ttk.Frame(advanced_controls_frame)
    ramp_container.grid(row=2, column=0, columnspan=3, pady=4)
    ramp_subsection_frame = ttk.LabelFrame(ramp_container, text="Ramp Settings")
    ramp_subsection_frame.pack()

    # --- Populate Background Noise subsection ---
    noise_type_label = ttk.Label(noise_subsection_frame, text="Noise Type:")
    noise_type_label.grid(row=0, column=0, padx=10, pady=4, sticky="e")

    noise_type_var = tk.StringVar(value="None")
    noise_type_combo = ttk.Combobox(
        noise_subsection_frame,
        textvariable=noise_type_var,
        values=["None", "White", "Pink", "Brown"],
        state="readonly",
        width=15
    )
    noise_type_combo.grid(row=0, column=1, padx=10, pady=4, sticky="w")

    noise_volume_label = ttk.Label(noise_subsection_frame, text="Volume (%):")
    noise_volume_label.grid(row=1, column=0, padx=10, pady=4, sticky="e")
    noise_volume_entry = ttk.Entry(noise_subsection_frame, width=10)
    noise_volume_entry.grid(row=1, column=1, padx=10, pady=4, sticky="w")
    noise_volume_entry.insert(0, "10")

    # --- Populate Ramp Settings subsection ---
    ramp_enabled_var = tk.BooleanVar(value=False)
    # Container for the switch to center it
    switch_container = ttk.Frame(ramp_subsection_frame)
    switch_container.grid(row=0, column=0, columnspan=2, pady=6)
    ramp_label = ttk.Label(switch_container, text="Enable Ramp")
    ramp_label.pack(side='left', padx=5)
    ramp_switch = tb.Checkbutton(switch_container, variable=ramp_enabled_var, bootstyle="success-round-toggle")
    ramp_switch.pack(side='left')

    carrier_label = ttk.Label(ramp_subsection_frame, text="Carrier (Hz):")
    carrier_label.grid(row=1, column=0, padx=10, pady=4, sticky="e")
    carrier_entry = ttk.Entry(ramp_subsection_frame, width=10)
    carrier_entry.grid(row=1, column=1, padx=10, pady=4, sticky="w")
    carrier_entry.insert(0, "432")

    start_beat_label = ttk.Label(ramp_subsection_frame, text="Start beat (Hz):")
    start_beat_label.grid(row=2, column=0, padx=10, pady=4, sticky="e")
    start_beat_entry = ttk.Entry(ramp_subsection_frame, width=10)
    start_beat_entry.grid(row=2, column=1, padx=10, pady=4, sticky="w")
    start_beat_entry.insert(0, "20")

    end_beat_label = ttk.Label(ramp_subsection_frame, text="End beat (Hz):")
    end_beat_label.grid(row=3, column=0, padx=10, pady=4, sticky="e")
    end_beat_entry = ttk.Entry(ramp_subsection_frame, width=10)
    end_beat_entry.grid(row=3, column=1, padx=10, pady=4, sticky="w")
    end_beat_entry.insert(0, "3")

    ramp_minutes_label = ttk.Label(ramp_subsection_frame, text="Duration (min):")
    ramp_minutes_label.grid(row=4, column=0, padx=10, pady=4, sticky="e")
    ramp_minutes_entry = ttk.Entry(ramp_subsection_frame, width=10)
    ramp_minutes_entry.grid(row=4, column=1, padx=10, pady=4, sticky="w")
    ramp_minutes_entry.insert(0, "30")

    # --- Bottom control bar ---
    bottom_frame = ttk.Frame(root)
    bottom_frame.grid(row=3, column=0, columnspan=3, pady=6, sticky="ew")
    bottom_frame.columnconfigure(0, weight=1)
    bottom_frame.columnconfigure(1, weight=1)
    bottom_frame.columnconfigure(2, weight=1)

    generate_button = ttk.Button(bottom_frame, text="Generate Beat", command=play_audio)
    generate_button.grid(row=0, column=0, sticky="e", padx=20)

    status_label = ttk.Label(bottom_frame, textvariable=status_var, anchor="center")
    status_label.grid(row=0, column=1, sticky="ew")

    stop_button = ttk.Button(bottom_frame, text="Stop", command=stop_audio)
    stop_button.grid(row=0, column=2, sticky="w", padx=20)

    # --- Modo visual (estroboscopio): fila propia en la barra inferior ---
    # Sin LabelFrame (su título robaba la altura que necesita la fila) y con
    # wraplength en la etiqueta: el texto largo de estado ensanchaba la ventana
    # y empujaba la columna de presets fuera de la pantalla.
    visual_toggle_button = tb.Button(
        bottom_frame, text="Modo visual", command=toggle_visual_mode,
        bootstyle="secondary")
    visual_toggle_button.grid(row=1, column=0, sticky="e", padx=20, pady=(0, 4))

    visual_status_label = ttk.Label(
        bottom_frame, text="Visual: -", anchor="center", justify="center",
        wraplength=640)
    visual_status_label.grid(row=1, column=1, sticky="ew", pady=(0, 4))

    visual_disclaimer_label = ttk.Label(
        bottom_frame, text="No es un dispositivo médico ni un tratamiento.",
        anchor="e")
    visual_disclaimer_label.grid(row=1, column=2, sticky="e", padx=20, pady=(0, 4))

    # El estado del gate se recalcula al cambiar ritmo, categoría o rampa
    beat_type_var.trace_add("write", lambda *a: update_visual_button())
    ramp_enabled_var.trace_add("write", lambda *a: update_visual_button())
    for visual_entry in (left_frequency_entry, right_frequency_entry,
                         start_beat_entry, end_beat_entry,
                         ramp_minutes_entry):
        visual_entry.bind("<KeyRelease>", lambda e: update_visual_button())
    update_visual_button()

    update_live_status()

    root.mainloop()
if __name__ == "__main__":
    main()
