import tkinter as tk
import json
import math  # NEW
import simpleaudio as sa  # NEW
import sys
import traceback
import numpy as np
import sounddevice as sd


SAMPLE_RATE = 44100  # NEW


class Note:
    def __init__(self, pitch, duration_beats):
        self.pitch = pitch
        self.duration_beats = duration_beats


class Score:
    def __init__(self, title, tempo_bpm, measures):
        self.title = title
        self.tempo_bpm = tempo_bpm
        self.measures = measures  # list[list[Note]]

    @classmethod
    def from_dict(cls, data):
        measures = []
        for m in data["measures"]:
            notes = [Note(n["pitch"], n["duration_beats"]) for n in m["notes"]]
            measures.append(notes)
        return cls(data["title"], data["tempo_bpm"], measures)

    def all_notes(self):
        for mi, measure in enumerate(self.measures):
            for ni, note in enumerate(measure):
                yield mi, ni, note


# === SOUND HELPERS (NEW) =====================================

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

    semitone_offset_from_A4 = NOTE_OFFSETS[name] + 12 * (octave - 4)
    freq = 440.0 * (2.0 ** (semitone_offset_from_A4 / 12.0))
    return freq

SAMPLE_RATE = 44100

SAMPLE_RATE = 44100

import math
import numpy as np
import sounddevice as sd

SAMPLE_RATE = 44100

def play_sine_note(
    pitch: str,
    duration_s: float,
    volume: float = 0.25,
    debug_label: str | None = None,
    fade_in_ms: float = 5.0,
    fade_out_ms: float = 5.0,
):
    freq = pitch_to_frequency(pitch)
    if freq <= 0.0 or duration_s <= 0:
        return None

    volume = float(max(0.0, min(volume, 1.0)))

    num_samples = int(SAMPLE_RATE * duration_s)
    if num_samples <= 0:
        return None

    # Base sine wave
    t = np.linspace(0, duration_s, num_samples, endpoint=False)
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32)

    # --- Envelope (fade in/out) ---
    fade_in_samples = int(SAMPLE_RATE * (fade_in_ms / 1000.0))
    fade_out_samples = int(SAMPLE_RATE * (fade_out_ms / 1000.0))

    # Clamp in case note is very short
    fade_in_samples = min(fade_in_samples, num_samples // 2)
    fade_out_samples = min(fade_out_samples, num_samples // 2)

    envelope = np.ones(num_samples, dtype=np.float32)

    if fade_in_samples > 0:
        envelope[:fade_in_samples] = np.linspace(0.0, 1.0, fade_in_samples, endpoint=True)
    if fade_out_samples > 0:
        envelope[-fade_out_samples:] = np.linspace(1.0, 0.0, fade_out_samples, endpoint=True)

    wave *= envelope
    wave *= volume  # scale overall volume

    if debug_label:
        print(
            f"[note {debug_label}] freq={freq:.2f}Hz duration={duration_s:.3f}s "
            f"samples={num_samples} fade_in={fade_in_samples} fade_out={fade_out_samples}"
        )

    # Play (blocking)
    sd.play(wave, SAMPLE_RATE)
    sd.wait()
    return None


# === PLAYER ===================================================


class Player:
    def __init__(self, root, score, update_ui_callback):
        self.root = root
        self.score = score
        self.update_ui = update_ui_callback
        self.is_playing = False
        self.current_index = 0
        self.notes_flat = list(score.all_notes())
        self.current_play_obj = None   # NEW

    def beats_to_ms(self, beats):
        beat_duration_s = 60.0 / self.score.tempo_bpm
        return int(beats * beat_duration_s * 1000)

    def beats_to_seconds(self, beats):
        beat_duration_s = 60.0 / self.score.tempo_bpm
        return beats * beat_duration_s

    def play(self):
        # if not self.is_playing:
        #     self.is_playing = True
        #     self.schedule_next()
        for idx, (m, b, note) in enumerate(self.notes_flat, start=1):
            play_sine_note(note.pitch, note.duration_beats,
                        volume=0.25, debug_label=str(idx))

    def pause(self):
        self.is_playing = False
        # optional: stop current note immediately
        if self.current_play_obj is not None:
            self.current_play_obj.stop()
            self.current_play_obj = None

    def stop(self):
        self.is_playing = False
        self.current_index = 0
        if self.current_play_obj is not None:
            self.current_play_obj.stop()
            self.current_play_obj = None
        self.update_ui(self.current_index, self.notes_flat)

    def schedule_next(self):
        if not self.is_playing or self.current_index >= len(self.notes_flat):
            self.is_playing = False
            # stop any ringing note at the end
            if self.current_play_obj is not None:
                self.current_play_obj.stop()
                self.current_play_obj = None
            return

        idx = self.current_index
        mi, ni, note = self.notes_flat[idx]
        self.update_ui(idx, self.notes_flat)

        duration_s = self.beats_to_seconds(note.duration_beats)

        # stop previous note (optional but safer)
        if self.current_play_obj is not None:
            self.current_play_obj.stop()

        # play this note and keep reference
        self.current_play_obj = play_sine_note(note.pitch, duration_s)

        # schedule the next one
        delay = int(duration_s * 1000)
        self.current_index += 1
        self.root.after(delay, self.schedule_next)

# === DEMO SCORE ===============================================


def make_demo_score():
    data = {
        "title": "Simple Flute Tune",
        "tempo_bpm": 80,
        "time_signature": [4, 4],
        "measures": [
            {
                "notes": [
                    {"pitch": "G4", "duration_beats": 2.0},
                    {"pitch": "C5", "duration_beats": 1.0},
                    {"pitch": "D5", "duration_beats": 1.0},
                    {"pitch": "E5", "duration_beats": 1.0},
                ]
            },
            {
                "notes": [
                    {"pitch": "F5", "duration_beats": 1.0},
                    {"pitch": "E5", "duration_beats": 1.0},
                    {"pitch": "D5", "duration_beats": 1.0},
                    {"pitch": "C5", "duration_beats": 1.0},
                ]
            },
        ],
    }
    return Score.from_dict(data)


# === UI =======================================================


def main():
    root = tk.Tk()
    root.title("Flute Practice Prototype")

    score = make_demo_score()
    label = tk.Label(root, font=("Arial", 24))
    label.pack(pady=20)

    def update_ui(current_idx, notes_flat):
        parts = []
        for i, (_, _, note) in enumerate(notes_flat):
            if i == current_idx:
                parts.append(f"[{note.pitch}]")
            else:
                parts.append(note.pitch)
        label.config(text=" ".join(parts))

    player = Player(root, score, update_ui)

    controls = tk.Frame(root)
    controls.pack(pady=10)

    tk.Button(controls, text="Start", command=player.play).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Pause", command=player.pause).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Stop", command=player.stop).pack(side=tk.LEFT, padx=5)

    update_ui(0, player.notes_flat)
    root.mainloop()


if __name__ == "__main__":
    main()
