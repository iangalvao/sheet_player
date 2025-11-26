# audio_engine.py
import math
import threading
from typing import Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100

NOTE_OFFSETS = {
    "C":  -9,
    "C#": -8, "Db": -8,
    "D":  -7,
    "D#": -6, "Eb": -6,
    "E":  -5,
    "F":  -4,
    "F#": -3, "Gb": -3,
    "G":  -2,
    "G#": -1, "Ab": -1,
    "A":   0,
    "A#":  1, "Bb": 1,
    "B":   2,
}

def pitch_to_frequency(pitch: str) -> float:
    if pitch.upper() == "REST":
        return 0.0
    i = 0
    while i < len(pitch) and not pitch[i].isdigit():
        i += 1
    name = pitch[:i]
    octave = int(pitch[i:])
    name = name.replace("♯", "#").replace("♭", "b")
    if name not in NOTE_OFFSETS:
        raise ValueError(f"Unknown pitch name: {pitch}")
    semitone_offset = NOTE_OFFSETS[name] + 12 * (octave - 4)
    return 440.0 * (2.0 ** (semitone_offset / 12.0))


class AudioEngine:
    """
    Simple 2-voice mixer:
      - note: precomputed buffer
      - click: short precomputed buffer

    Everything is mixed in one OutputStream callback.
    """
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

        # note voice
        self._note_wave: Optional[np.ndarray] = None
        self._note_index: int = 0
        self._note_active: bool = False

        # click voice
        self._click_wave: Optional[np.ndarray] = None
        self._click_index: int = 0
        self._click_active: bool = False

        self._lock = threading.Lock()

        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    # ---------- helpers ----------

    def _make_sine(self, freq: float, duration_s: float,
                   volume: float = 0.25,
                   fade_in_ms: float = 5.0,
                   fade_out_ms: float = 5.0) -> np.ndarray:
        if freq <= 0.0 or duration_s <= 0:
            return np.zeros(0, dtype=np.float32)

        volume = float(max(0.0, min(volume, 1.0)))
        num_samples = int(self.sample_rate * duration_s)
        if num_samples <= 0:
            return np.zeros(0, dtype=np.float32)

        t = np.linspace(0, duration_s, num_samples, endpoint=False)
        wave = np.sin(2 * math.pi * freq * t).astype(np.float32)

        # basic envelope
        fade_in_samples = int(self.sample_rate * (fade_in_ms / 1000.0))
        fade_out_samples = int(self.sample_rate * (fade_out_ms / 1000.0))
        fade_in_samples = min(fade_in_samples, num_samples // 2)
        fade_out_samples = min(fade_out_samples, num_samples // 2)

        envelope = np.ones(num_samples, dtype=np.float32)
        if fade_in_samples > 0:
            envelope[:fade_in_samples] = np.linspace(0.0, 1.0, fade_in_samples)
        if fade_out_samples > 0:
            envelope[-fade_out_samples:] = np.linspace(1.0, 0.0, fade_out_samples)

        wave *= envelope * volume
        return wave

    # ---------- public API ----------

    def play_note(self, pitch: str, duration_s: float, volume: float = 0.25):
        freq = pitch_to_frequency(pitch)
        wave = self._make_sine(freq, duration_s, volume,
                               fade_in_ms=5.0, fade_out_ms=20.0)

        with self._lock:
            if wave.size == 0:
                self._note_active = False
                self._note_wave = None
                self._note_index = 0
            else:
                self._note_wave = wave
                self._note_index = 0
                self._note_active = True

    def trigger_click(self, strong: bool = False):
        freq = 1200.0 if strong else 800.0
        duration_s = 0.06 if strong else 0.04
        volume = 0.4 if strong else 0.3

        wave = self._make_sine(freq, duration_s, volume,
                               fade_in_ms=1.0, fade_out_ms=10.0)

        with self._lock:
            self._click_wave = wave
            self._click_index = 0
            self._click_active = wave.size > 0

    def close(self):
        self._stream.stop()
        self._stream.close()

    # ---------- callback ----------

    def _callback(self, outdata, frames, time, status):
        if status:
            # You can print/log status if needed
            pass

        buf = np.zeros(frames, dtype=np.float32)

        with self._lock:
            # NOTE voice
            if self._note_active and self._note_wave is not None:
                remaining = len(self._note_wave) - self._note_index
                if remaining > 0:
                    to_copy = min(frames, remaining)
                    buf[:to_copy] += self._note_wave[
                        self._note_index:self._note_index + to_copy
                    ]
                    self._note_index += to_copy
                if self._note_index >= len(self._note_wave):
                    self._note_active = False
                    self._note_wave = None
                    self._note_index = 0

            # CLICK voice
            if self._click_active and self._click_wave is not None:
                remaining = len(self._click_wave) - self._click_index
                if remaining > 0:
                    to_copy = min(frames, remaining)
                    buf[:to_copy] += self._click_wave[
                        self._click_index:self._click_index + to_copy
                    ]
                    self._click_index += to_copy
                if self._click_index >= len(self._click_wave):
                    self._click_active = False
                    self._click_wave = None
                    self._click_index = 0

        # Simple safety limiter to avoid clipping
        np.clip(buf, -1.0, 1.0, out=buf)
        outdata[:] = buf.reshape(-1, 1)
