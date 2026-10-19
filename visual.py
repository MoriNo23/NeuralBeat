# visual.py
# Núcleo del modo visual estroboscópico (openspec/changes/modo-visual-estroboscopico).
#
# Módulo puro (solo stdlib): capacidad de pantalla, patrones de fotogramas,
# calibración de refresco, reloj de pulso de audio y scheduler de flips por
# deadlines absolutos. La capa Tk vive en SourceCode.py.
#
# Reglas de gate (design.md, decisión 2), con refresh medido R y ritmo pedido f:
#   - f > (R/2)(1 + tol)  -> no_disponible (no existe fundamental presentable;
#     emitir f "a la brava" alíasea a ~|R - f|, banda equivocada).
#   - existe n entero con |R/n - f|/f <= tol -> exacto (patrón fijo, duty ~50%,
#     jitter 0). Ej.: 59.8 Hz -> 29.9 (n=2), 19.93 (n=3), 9.97 (n=6).
#   - resto -> aproximado con patrón periódico (ventana <= ~1 s) y jitter de
#     un fotograma reportado.
#   - armónico (opt-in): pulsos a R/n con duty ~1/3 cuyo 2º armónico (2R/n)
#     aproxima f; |c2|/|c1| = 0.5 para duty 1/3; etiquetado experimental.

import math
import statistics
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Constantes de UI / seguridad
# --------------------------------------------------------------------------

# Parejas (apagado, encendido) por intensidad. "cómoda" = contraste moderado
# (menor potencia, por defecto); "brillante" = contraste máximo (opt-in).
INTENSITY_PAIRS = {
    "comoda": ("#202020", "#C9C9C9"),
    "brillante": ("#000000", "#FFFFFF"),
}

DEFAULT_INTENSITY = "comoda"

# Refresco por defecto cuando no hay calibración válida (etiqueta de baja
# confianza; se recomienda recalibrar en pantalla real).
DEFAULT_REFRESH_HZ = 60.0

# Tolerancia de clasificación (1%): el ritmo entregado se re-etiqueta con su
# frecuencia efectiva real cuando difiere de la pedida.
TOLERANCE_PCT = 1.0

# Tolerancia de emparejamiento para el armónico (2R/n vs f).
HARMONIC_TOLERANCE_PCT = 2.0

# Estados del gate.
STATE_EXACTO = "exacto"
STATE_APROXIMADO = "aproximado"
STATE_ARMONICO = "armonico"
STATE_NO_DISPONIBLE = "no_disponible"

# Orden de "peor" para el gate de rampa (menor = peor).
_STATE_RANK = {
    STATE_NO_DISPONIBLE: 0,
    STATE_ARMONICO: 1,
    STATE_APROXIMADO: 2,
    STATE_EXACTO: 3,
}


# --------------------------------------------------------------------------
# Capacidad y patrones
# --------------------------------------------------------------------------

@dataclass
class VisualCapability:
    """Resultado del gate para un ritmo pedido sobre un refresco medido."""
    state: str
    # Frecuencia efectiva (fundamental realmente emitida, Hz).
    effective_hz: Optional[float] = None
    # Frecuencia pedida que originó esta capacidad (para etiquetas).
    requested_hz: Optional[float] = None
    # Fotogramas por período (patrón fijo) para exacto/armónico.
    frames_per_period: Optional[int] = None
    # Patrón de fotogramas del período/ventana (True = encendido).
    pattern: Optional[List[bool]] = None
    # Ciclos de pulso de audio por ventana de patrón (para el scheduler).
    cycles_per_window: int = 1
    # Jitter esperado del parpadeo (ms). 0 para exacto y armónico.
    jitter_ms: Optional[float] = None
    # Desviación de frecuencia efectiva vs pedida (fracción, valor absoluto).
    freq_error: Optional[float] = None
    # Razón legible cuando no está disponible.
    reason: Optional[str] = None
    # Refresco usado para el cálculo (Hz).
    refresh_hz: Optional[float] = None
    # Solo para armónico: frecuencia que el 2º armónico aproxima (Hz).
    harmonic_of_hz: Optional[float] = None

    @property
    def available(self) -> bool:
        return self.state in (STATE_EXACTO, STATE_APROXIMADO, STATE_ARMONICO)


def pulse_train_coefficient(k: int, duty: float) -> float:
    """Magnitud del coeficiente k del tren de pulsos rectangulares de duty d.

    c_k ∝ |sin(pi * k * d)| / k (normalizado a c_1 = 1 cuando duty = 1/2... en
    general la razón entre coeficientes es lo que importa).
    """
    if k < 1:
        raise ValueError("k debe ser >= 1")
    return abs(math.sin(math.pi * k * duty)) / k


def harmonic_amplitude_ratio(duty: float = 1.0 / 3.0, k: int = 2) -> float:
    """|c_k| / |c_1| para un tren de pulsos de duty dado (duty 1/3, k=2 -> 0.5)."""
    c1 = pulse_train_coefficient(1, duty)
    if c1 <= 0:
        return float("inf")
    return pulse_train_coefficient(k, duty) / c1


def _exact_pattern(n: int) -> List[bool]:
    """Patrón de n fotogramas, duty ~50%, arrancando en el inicio del pulso."""
    on = max(1, (n + 1) // 2)
    return [True] * on + [False] * (n - on)


def _window_pattern(w_frames: int, cycles: int) -> List[bool]:
    """Patrón periódico de w_frames con `cycles` pulsos (~50% de duty).

    Los 2*cycles semiciclos se reparten con distribución tipo Bresenham
    (fronteras en round(k * w / (2*cycles))).
    """
    half = w_frames / (2.0 * cycles)
    pattern = [False] * w_frames
    for k in range(2 * cycles):
        start = int(round(k * half))
        end = int(round((k + 1) * half))
        if k % 2 == 0:  # semiciclo encendido
            for i in range(start, min(end, w_frames)):
                pattern[i] = True
    return pattern


def _harmonic_pattern(n: int) -> List[bool]:
    """Patrón de n fotogramas, duty ~1/3 (n=3 -> 1 encendido, 2 apagados)."""
    on = max(1, int(round(n / 3.0)))
    return [True] * on + [False] * (n - on)


def harmonic_candidate(rate_hz: float, refresh_hz: float,
                       tolerance_pct: float = HARMONIC_TOLERANCE_PCT
                       ) -> Optional[VisualCapability]:
    """Busca n tal que el 2º armónico de pulsos a R/n (duty 1/3) aproxime rate.

    Devuelve None si no hay candidato dentro de la tolerancia.
    """
    if rate_hz <= 0 or refresh_hz <= 0:
        return None
    n_guess = 2.0 * refresh_hz / rate_hz
    for n in {max(3, int(round(n_guess)) - 1), int(round(n_guess)) + 1, max(3, int(round(n_guess)))}:
        if n < 3:
            continue
        fundamental = refresh_hz / n
        second = 2.0 * fundamental
        err = abs(second - rate_hz) / rate_hz
        if err * 100.0 <= tolerance_pct:
            return VisualCapability(
                state=STATE_ARMONICO,
                effective_hz=fundamental,
                requested_hz=rate_hz,
                frames_per_period=n,
                pattern=_harmonic_pattern(n),
                cycles_per_window=1,
                jitter_ms=0.0,
                freq_error=err,
                refresh_hz=refresh_hz,
                harmonic_of_hz=second,
            )
    return None


def best_substitute(refresh_hz: float) -> VisualCapability:
    """Ritmo exacto más alto soportado (R/2, 2 fotogramas, duty 50%)."""
    cap = visual_capability(refresh_hz / 2.0, refresh_hz)
    cap.requested_hz = None  # es una frecuencia DISTINTA a la pedida
    return cap


def visual_capability(rate_hz: float, refresh_hz: float,
                      harmonics_enabled: bool = False,
                      tolerance_pct: float = TOLERANCE_PCT
                      ) -> VisualCapability:
    """Clasifica `rate_hz` sobre una pantalla de `refresh_hz` medidos.

    Función pura: estado, fotogramas por período, frecuencia efectiva y jitter
    esperado (tasks.md 1.1). Nunca entrega exacto/aproximado cuando el ritmo
    excede la mitad del refresco (rechazo de emisión cruda, tasks.md 1.3).
    """
    if refresh_hz is None or refresh_hz <= 0:
        return VisualCapability(
            state=STATE_NO_DISPONIBLE, requested_hz=rate_hz,
            reason="no hay calibración de pantalla válida (recalibra en Settings)",
            refresh_hz=refresh_hz)
    if rate_hz is None or rate_hz <= 0:
        return VisualCapability(
            state=STATE_NO_DISPONIBLE, requested_hz=rate_hz,
            reason="ritmo no válido (debe ser > 0 Hz)", refresh_hz=refresh_hz)

    limit_hz = refresh_hz / 2.0 * (1.0 + tolerance_pct / 100.0)

    # Gate duro: por encima de R/2 no existe fundamental presentable.
    if rate_hz > limit_hz:
        if harmonics_enabled:
            harm = harmonic_candidate(rate_hz, refresh_hz)
            if harm is not None:
                return harm
        return VisualCapability(
            state=STATE_NO_DISPONIBLE, requested_hz=rate_hz,
            reason=(f"{rate_hz:.2f} Hz supera la mitad del refresco medido "
                    f"(máximo {refresh_hz / 2.0:.1f} Hz en {refresh_hz:.1f} Hz de pantalla)"),
            refresh_hz=refresh_hz)

    # Exacto: período entero de fotogramas dentro de tolerancia.
    n0 = refresh_hz / rate_hz
    candidates = {max(2, int(round(n0)) - 1), int(round(n0)), max(2, int(round(n0)) + 1)}
    best_n, best_err = None, None
    for n in sorted(candidates):
        if n < 2:
            continue
        err = abs(refresh_hz / n - rate_hz) / rate_hz
        if best_err is None or err < best_err:
            best_n, best_err = n, err
    if best_err is not None and best_err * 100.0 <= tolerance_pct:
        eff = refresh_hz / best_n
        return VisualCapability(
            state=STATE_EXACTO,
            effective_hz=eff,
            requested_hz=rate_hz,
            frames_per_period=best_n,
            pattern=_exact_pattern(best_n),
            cycles_per_window=1,
            jitter_ms=0.0,
            freq_error=best_err,
            refresh_hz=refresh_hz)

    # Aproximado: ventana periódica (<= ~1 s) con m ciclos, mínimo error.
    max_cycles = max(1, int(rate_hz))
    best = None  # (err, m, w)
    for m in range(1, max_cycles + 1):
        w = int(round(m * refresh_hz / rate_hz))
        w = max(w, 2 * m)
        if m > 1 and w > int(refresh_hz):  # ventana <= ~1 s (m=1 siempre se permite)
            continue
        err = abs(m * refresh_hz / w - rate_hz) / rate_hz
        if best is None or err < best[0] - 1e-12:
            best = (err, m, w)
    if best is None or best[0] * 100.0 > 5.0:
        return VisualCapability(
            state=STATE_NO_DISPONIBLE, requested_hz=rate_hz,
            reason=("no hay patrón periódico de fotogramas <= 1 s que aproxime "
                    f"{rate_hz:.2f} Hz en {refresh_hz:.1f} Hz de pantalla"),
            refresh_hz=refresh_hz)

    err, m, w = best
    eff = m * refresh_hz / w
    return VisualCapability(
        state=STATE_APROXIMADO,
        effective_hz=eff,
        requested_hz=rate_hz,
        frames_per_period=None,
        pattern=_window_pattern(w, m),
        cycles_per_window=m,
        jitter_ms=1000.0 / refresh_hz,
        freq_error=err,
        refresh_hz=refresh_hz)


def ramp_gate_capability(start_hz: float, end_hz: float, refresh_hz: float,
                         harmonics_enabled: bool = False,
                         n_points: int = 65,
                         tolerance_pct: float = TOLERANCE_PCT
                         ) -> VisualCapability:
    """Gate de rampa: se evalúa con el PEOR punto del barrido (tasks.md 1.3).

    Muestrea el barrido lineal [start_hz, end_hz] y devuelve la capacidad del
    punto con peor estado (no_disponible < armonico < aproximado < exacto).
    """
    if n_points < 2:
        n_points = 2
    worst = None
    for i in range(n_points):
        f = start_hz + (end_hz - start_hz) * i / (n_points - 1)
        cap = visual_capability(f, refresh_hz, harmonics_enabled, tolerance_pct)
        if worst is None or _STATE_RANK[cap.state] < _STATE_RANK[worst.state]:
            worst = cap
    return worst


# --------------------------------------------------------------------------
# Etiquetas (feedback de potencia, tasks.md 4.4)
# --------------------------------------------------------------------------

def capability_label(cap: VisualCapability, requested_hz: Optional[float] = None) -> str:
    """Etiqueta de estado para el botón/UI (con feedback de potencia)."""
    if cap is None:
        return "Modo visual: sin datos"
    req = requested_hz if requested_hz is not None else cap.requested_hz

    if cap.state == STATE_EXACTO:
        txt = "exacto"
        if cap.effective_hz is not None and req is not None:
            if abs(cap.effective_hz - req) / req > 0.001:
                txt += f" @ {cap.effective_hz:.2f} Hz"
        return txt.capitalize() if txt else "Exacto"

    if cap.state == STATE_APROXIMADO:
        jitter = cap.jitter_ms or 0.0
        eff = f" @ {cap.effective_hz:.2f} Hz" if cap.effective_hz else ""
        return f"Aproximado{eff} · jitter ±{jitter:.0f} ms"

    if cap.state == STATE_ARMONICO:
        harm = cap.harmonic_of_hz or (2.0 * (cap.effective_hz or 0.0))
        fund = cap.effective_hz or 0.0
        return (f"≈{harm:.2f} Hz por armónico · experimental "
                f"(fundamental {fund:.2f} Hz, potencia menor)")

    # no_disponible
    reason = cap.reason or "ritmo no soportado por la pantalla"
    return f"No disponible: {reason}"


def intensity_note(intensity: str) -> str:
    """Nota de potencia para la intensidad elegida (specs: feedback)."""
    if intensity == "brillante":
        return "intensidad brillante: máximo contraste (mayor respuesta visual)"
    return "intensidad cómoda: respuesta visual menor que en brillante"


# --------------------------------------------------------------------------
# Calibración de refresco (tasks.md 2.1)
# --------------------------------------------------------------------------

def compute_refresh_stats(timestamps: Sequence[float]) -> Tuple[float, float]:
    """Estadísticas de refresco a partir de marcas de presentación.

    Devuelve (refresh_hz, jitter_ms): mediana de 1/delta y p95 del desvío
    absoluto de los deltas (en ms). Se descartan el primer delta y extremos.
    """
    if len(timestamps) < 8:
        raise ValueError("se necesitan al menos 8 marcas para estadísticas")
    deltas = [b - a for a, b in zip(timestamps, timestamps[1:])]
    deltas = [d for d in deltas if d > 0]
    if len(deltas) < 6:
        raise ValueError("deltas no positivos: medición inválida")
    med = statistics.median(deltas)
    refresh_hz = 1.0 / med
    devs = [abs(d - med) for d in deltas]
    jitter_ms = _percentile(devs, 95) * 1000.0
    return refresh_hz, jitter_ms


def _percentile(sortedable: Sequence[float], pct: float) -> float:
    """Percentil por interpolación lineal (equivalente a numpy p95)."""
    data = sorted(sortedable)
    if not data:
        return 0.0
    if len(data) == 1:
        return data[0]
    k = (len(data) - 1) * (pct / 100.0)
    f = int(math.floor(k))
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def validate_refresh_measurement(refresh_hz: float, jitter_ms: float
                                 ) -> Tuple[bool, str]:
    """Valida plausibilidad de la medición. Devuelve (ok, confianza)."""
    if not (23.0 <= refresh_hz <= 250.0):
        return False, "baja"
    if jitter_ms > 6.0:
        return False, "baja"
    if jitter_ms > 3.0:
        return True, "media"
    return True, "alta"


# --------------------------------------------------------------------------
# Configuración persistente (tasks.md 2.2)
# --------------------------------------------------------------------------

def merge_visual_config(cfg: dict) -> dict:
    """Fusiona la sección "visual" de config con valores por defecto.

    Compatibilidad hacia atrás: una config sin la clave "visual" (o con claves
    parciales) no rompe; los valores ausentes toman los defaults.
    """
    raw = cfg.get("visual") if isinstance(cfg, dict) else None
    if not isinstance(raw, dict):
        raw = {}

    def _num(key):
        try:
            v = raw.get(key)
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    refresh = _num("refresh_hz")
    jitter = _num("jitter_ms")
    consent = raw.get("photosensitive_consent")
    intensity = raw.get("intensity")
    harmonics = raw.get("harmonics_enabled")

    return {
        "refresh_hz": refresh if (refresh and refresh > 0) else None,
        "jitter_ms": jitter if (jitter is not None and jitter >= 0) else None,
        "calibrated_at": raw.get("calibrated_at") if isinstance(raw.get("calibrated_at"), str) else None,
        "confidence": raw.get("confidence") if isinstance(raw.get("confidence"), str) else None,
        "photosensitive_consent": bool(consent),
        "intensity": intensity if intensity in INTENSITY_PAIRS else DEFAULT_INTENSITY,
        "harmonics_enabled": bool(harmonics),
    }


# --------------------------------------------------------------------------
# Reloj de pulso de audio (fase del ritmo de audio en tiempo de audio)
# --------------------------------------------------------------------------

class BeatClock:
    """Ciclos acumulados del pulso de audio en función del tiempo de audio.

    Constante: cycles(t) = f * t.
    Rampa lineal (como _compute_ramped_beat_hz de SourceCode.py):
        f(t) = f0 + (f1 - f0) * clip(t / T, 0, 1)
        cycles(t) = f0*t + (f1-f0)*t^2/(2T)  para t <= T; lineal después.
    """

    def __init__(self, rate_hz: Optional[float] = None,
                 start_hz: Optional[float] = None,
                 end_hz: Optional[float] = None,
                 ramp_s: Optional[float] = None):
        if start_hz is None or end_hz is None or not ramp_s:
            self.constant = True
            self.f0 = float(rate_hz or 0.0)
            self.f1 = self.f0
            self.T = 0.0
        else:
            self.constant = False
            self.f0 = float(start_hz)
            self.f1 = float(end_hz)
            self.T = float(ramp_s)
        if self.f0 <= 0 or self.f1 <= 0:
            raise ValueError("la frecuencia de pulso debe ser > 0")

    def rate_at(self, t: float) -> float:
        if self.constant or t >= self.T:
            return self.f1
        if t <= 0:
            return self.f0
        return self.f0 + (self.f1 - self.f0) * (t / self.T)

    def cycles(self, t: float) -> float:
        if self.constant:
            return self.f0 * t
        if t <= 0:
            return 0.0
        if t >= self.T:
            c_T = self.f0 * self.T + (self.f1 - self.f0) * self.T / 2.0
            return c_T + self.f1 * (t - self.T)
        return self.f0 * t + (self.f1 - self.f0) * t * t / (2.0 * self.T)

    def next_boundary(self, t: float) -> float:
        """Tiempo de audio de la siguiente frontera de pulso tras t."""
        c = self.cycles(t)
        k = math.floor(c) + 1.0
        lo, hi = t, t + (k - c) / min(self.f0, self.f1) + 1.0
        for _ in range(60):  # bisección monótona (robusta para rampas)
            mid = (lo + hi) / 2.0
            if self.cycles(mid) < k:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2.0


# --------------------------------------------------------------------------
# Scheduler de flips por deadlines absolutos (design.md decisión 4, tasks 3.2)
# --------------------------------------------------------------------------

class StrobeScheduler:
    """Scheduler de parpadeo anclado al reloj de audio (samples_generated).

    - Posición del patrón: fase del pulso de AUDIO (BeatClock), no el reloj del
      sistema: el primer pulso visual se alinea a una frontera de pulso de
      audio y la fase queda enganchada a la del audio.
    - Entre re-anclajes (~1 s) el tiempo de audio se extrapola con el reloj del
      sistema; en cada re-anclaje se ajusta a samples_generated real (absorbe
      la deriva del cristal).
    - Flips por deadlines absolutos: poll(now) emite el estado que corresponde
      a `now`; los flips tardíos SE SALTAN (salto directo al estado correcto,
      sin acumular atraso).
    - Modo free-running (armónico): el patrón avanza al ritmo de fotogramas R
      anclado a la frontera de pulso (fundamental exacta R/n, jitter 0).
    """

    def __init__(self, pattern: Sequence[bool], refresh_hz: float,
                 on_flip: Callable[[bool], None],
                 clock: Callable[[], float],
                 get_audio_time: Callable[[], float],
                 beat_clock: BeatClock,
                 cycles_per_window: int = 1,
                 free_running: bool = False,
                 reanchor_interval_s: float = 1.0,
                 rebuild_fn: Optional[Callable[[float], Optional[Tuple[List[bool], int]]]] = None):
        self.pattern = [bool(p) for p in pattern]
        if not self.pattern:
            raise ValueError("el patrón no puede estar vacío")
        self.W = len(self.pattern)
        self.refresh_hz = float(refresh_hz)
        self.on_flip = on_flip
        self.clock = clock
        self.get_audio_time = get_audio_time
        self.beat_clock = beat_clock
        self.cpw = max(1, int(cycles_per_window))
        self.free_running = bool(free_running)
        self.reanchor_interval_s = float(reanchor_interval_s)
        self.rebuild_fn = rebuild_fn

        self.started = False
        self.stalled = False
        self.state: Optional[bool] = None
        self.sys_ref = 0.0
        self.audio_ref = 0.0
        self.align_audio = 0.0
        self.phase0 = 0.0
        self.last_flip_lateness: Optional[float] = None
        self._prev_deadline: Optional[float] = None

    # -- ciclo de vida ------------------------------------------------------

    def start(self) -> float:
        """Arranca alineado a la siguiente frontera de pulso de audio.

        Devuelve el deadline (tiempo de reloj) del primer flip previsto.
        """
        audio0 = self.get_audio_time()
        self.align_audio = self.beat_clock.next_boundary(audio0)
        # La bisección converge con un epsilon por encima del ciclo entero:
        # se redondea para no caer en el lado equivocado de la frontera.
        self.phase0 = float(round(self.beat_clock.cycles(self.align_audio)))
        self._snap(self.clock(), audio0)
        self.started = True
        self.stalled = False
        self.state = None
        return self.poll()

    def stop(self) -> None:
        self.started = False

    def _snap(self, sys_now: float, audio_now: float) -> None:
        self.sys_ref = sys_now
        self.audio_ref = audio_now

    def _audio_est(self, sys_now: float) -> float:
        return self.audio_ref + (sys_now - self.sys_ref)

    # -- posición del patrón -------------------------------------------------

    def _pos_frames(self, audio_t: float) -> float:
        """Posición (float, en fotogramas) dentro de la ventana del patrón."""
        if self.free_running:
            return (audio_t - self.align_audio) * self.refresh_hz
        phase = self.beat_clock.cycles(audio_t) - self.phase0
        return (phase % self.cpw) / self.cpw * self.W

    def _state_at(self, audio_t: float) -> bool:
        frame = math.floor(self._pos_frames(audio_t))
        return self.pattern[frame % self.W]

    def _next_crossing(self, sys_now: float) -> float:
        """Deadline (tiempo de reloj) del próximo cambio de estado del patrón."""
        audio_t = self._audio_est(sys_now)
        p = self._pos_frames(audio_t)
        target = math.floor(p) + 1.0
        if target >= self.W:  # envuelve al inicio de la ventana
            target = float(self.W)
        delta_frames = target - p
        if self.free_running:
            delta_audio = delta_frames / self.refresh_hz
        else:
            rate = max(self.beat_clock.rate_at(audio_t), 1e-6)
            delta_cycles = delta_frames * self.cpw / self.W
            delta_audio = delta_cycles / rate
        return sys_now + delta_audio

    # -- bucle principal -----------------------------------------------------

    def poll(self, now: Optional[float] = None) -> Optional[float]:
        """Procesa flips vencidos a `now`; devuelve el próximo deadline.

        Si llega tarde, salta directamente al estado que corresponde a `now`
        (no emite los flips intermedios perdidos: no acumula atraso).
        """
        if not self.started:
            return None
        now = self.clock() if now is None else now

        # Re-anclaje periódico al contador real de audio.
        if now - self.sys_ref >= self.reanchor_interval_s:
            audio_now = self.get_audio_time()
            if audio_now <= self.audio_ref:
                self.stalled = True  # el audio no avanza (parado/terminado)
            self._snap(now, audio_now)
            if self.rebuild_fn is not None and not self.stalled:
                rebuilt = self.rebuild_fn(self.beat_clock.rate_at(audio_now))
                if rebuilt is not None:
                    new_pattern, new_cpw = rebuilt
                    if new_pattern != self.pattern or new_cpw != self.cpw:
                        self.pattern = [bool(p) for p in new_pattern]
                        self.W = len(self.pattern)
                        self.cpw = max(1, int(new_cpw))

        if self.stalled:
            return None

        audio_t = self._audio_est(now)
        target = self._state_at(audio_t)
        if target != self.state:
            self.state = target
            if self._prev_deadline is not None and now > self._prev_deadline:
                self.last_flip_lateness = now - self._prev_deadline
            self.on_flip(target)

        deadline = self._next_crossing(now)
        self._prev_deadline = deadline
        return deadline


class LatenessMonitor:
    """Aborta si la mediana de lateness supera un umbral (design.md decisión 7).

    Guarda (now, lateness_s) de los últimos `window_s` y expone should_abort()
    cuando la mediana de lateness > ratio * frame_period_s.
    """

    def __init__(self, frame_period_s: float, ratio: float = 0.15,
                 window_s: float = 2.0, min_samples: int = 8):
        self.frame_period_s = float(frame_period_s)
        self.ratio = float(ratio)
        self.window_s = float(window_s)
        self.min_samples = int(min_samples)
        self._samples: List[Tuple[float, float]] = []

    def record(self, now: float, lateness_s: float) -> None:
        self._samples.append((now, max(0.0, lateness_s)))
        cutoff = now - self.window_s
        self._samples = [s for s in self._samples if s[0] >= cutoff]

    def should_abort(self) -> bool:
        if len(self._samples) < self.min_samples:
            return False
        med = statistics.median([lat for _, lat in self._samples])
        return med > self.ratio * self.frame_period_s
