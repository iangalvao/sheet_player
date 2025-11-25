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
    Simple two-voice mixer:
      - voice 1: current note (sine, with envelope)
      - voice 2: short click for metronome

    One continuous OutputStream with a callback that mixes both.
    """
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate

        # --- note voice state ---
        self._note_active = False
        self._note_freq = 0.0
        self._note_phase = 0.0
        self._note_remaining_samples = 0
        self._note_volume = 0.25

        # --- click voice state ---
        self._click_wave: Optional[np.ndarray] = None
        self._click_index = 0
        self._click_active = False

        self._lock = threading.Lock()

        # Start stream
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    # ========== PUBLIC API ==========

    def play_note(self, pitch: str, duration_s: float, volume: float = 0.25):
        freq = pitch_to_frequency(pitch)
        if freq <= 0.0 or duration_s <= 0:
            # treat as rest: just turn note off
            with self._lock:
                self._note_active = False
            return

        num_samples = int(self.sample_rate * duration_s)
        if num_samples <= 0:
            return

        with self._lock:
            self._note_freq = freq
            self._note_phase = 0.0
            self._note_remaining_samples = num_samples
            self._note_volume = float(max(0.0, min(volume, 1.0)))
            self._note_active = True

    def trigger_click(self, strong: bool = False):
        """
        Prepare a short click waveform that the callback will mix on top.
        """
        freq = 1200.0 if strong else 800.0
        duration_s = 0.06 if strong else 0.04
        volume = 0.4 if strong else 0.3

        num_samples = int(self.sample_rate * duration_s)
        if num_samples <= 0:
            return

        t = np.linspace(0, duration_s, num_samples, endpoint=False)
        wave = np.sin(2 * math.pi * freq * t).astype(np.float32)

        # fast attack, slightly longer release to avoid clicks
        fade_in_samples = max(1, int(self.sample_rate * 0.001))
        fade_out_samples = max(1, int(self.sample_rate * 0.01))
        fade_in_samples = min(fade_in_samples, num_samples // 2)
        fade_out_samples = min(fade_out_samples, num_samples // 2)

        envelope = np.ones(num_samples, dtype=np.float32)
        envelope[:fade_in_samples] = np.linspace(0.0, 1.0, fade_in_samples)
        envelope[-fade_out_samples:] = np.linspace(1.0, 0.0, fade_out_samples)

        wave *= envelope * volume

        with self._lock:
            self._click_wave = wave
            self._click_index = 0
            self._click_active = True

    def close(self):
        self._stream.stop()
        self._stream.close()

    # ========== CALLBACK ==========

    def _callback(self, outdata, frames, time, status):
        if status:
            # You could log this
            pass

        buf = np.zeros(frames, dtype=np.float32)

        with self._lock:
            # --- Note voice ---
            if self._note_active and self._note_remaining_samples > 0:
                to_generate = min(frames, self._note_remaining_samples)
                # simple oscillator with continuity of phase
                # phase_inc = 2.0 * math.pi * self._note_freq / (self.sample_rate)
                phase_inc = 2.0 * math.pi * self._note_freq / (self.sample_rate)
                phases = self._note_phase + phase_inc * np.arange(to_generate, dtype=np.float32)
                self._note_phase = float(phases[-1] + phase_inc)

                # basic envelope: fade in/out 5ms
                env = np.ones(to_generate, dtype=np.float32)
                total = self._note_remaining_samples
                # approximate fade on first/last 5ms of the note
                fade_samples = int(self.sample_rate * 0.005)
                fade_samples = min(fade_samples, total // 2, to_generate)

                if fade_samples > 0:
                    # If we're at the very beginning of the note
                    if self._note_remaining_samples == total:
                        env[:fade_samples] *= np.linspace(0.0, 1.0, fade_samples)
                    # If we're near the end
                    if self._note_remaining_samples <= fade_samples:
                        env_tail = np.linspace(1.0, 0.0, fade_samples)
                        env[-fade_samples:] *= env_tail[-fade_samples:]

                note_wave = np.sin(phases) * env * self._note_volume * 0.5

                buf[:to_generate] += note_wave
                self._note_remaining_samples -= to_generate
                if self._note_remaining_samples <= 0:
                    self._note_active = False

            # --- Click voice ---
            if self._click_active and self._click_wave is not None:
                remaining = len(self._click_wave) - self._click_index
                if remaining > 0:
                    to_copy = min(frames, remaining)
                    buf[:to_copy] += self._click_wave[self._click_index:self._click_index + to_copy]
                    self._click_index += to_copy
                if self._click_index >= len(self._click_wave):
                    self._click_active = False
                    self._click_wave = None
                    self._click_index = 0

        outdata[:] = buf.reshape(-1, 1)
