# editor.py
from __future__ import annotations

from typing import Callable, List, Tuple, Optional
from engine.timebase import BeatTime
from domain.score import Note, Score


class EditorController:
    """
    Responsible for:
    - Holding the current Score
    - Keeping a flattened (measure_index, note_index, Note) list
    - Tracking the selected *note* index
    - Interval selection (measure + beat_start/end)
    - Applying edits (for now: transpose selected note)
    """

    def __init__(self, score: Score):
        self.score: Score = score
        self.selected_index: int = 0
        # (measure_idx, note_idx, Note)
        self._notes_flat: List[Tuple[int, int, Note]] = []
        self._rebuild_flat()

        # Selection mode: "note" or "interval"
        self._selection_mode: str = "note"
        # (measure_index, beat_start, beat_end)
        self._selection_interval: Optional[Tuple[int, BeatTime, BeatTime]] = None

    # ----- internal helpers ------------------------------------

    def _rebuild_flat(self) -> None:
        """Rebuild the flat list from the current score."""
        self._notes_flat = list(self.score.all_notes())

    # ----- score / flat notes API ------------------------------

    def set_score(self, score: Score) -> None:
        """Replace the score and reset selection + interval."""
        self.score = score
        self.selected_index = 0
        self._selection_mode = "note"
        self._selection_interval = None
        self._rebuild_flat()

    def get_flat_notes(self) -> List[Tuple[int, int, Note]]:
        """Return the current flattened notes."""
        return self._notes_flat

    def has_notes(self) -> bool:
        return bool(self._notes_flat)

    # ----- selection mode + interval ---------------------------

    def get_selection_mode(self) -> str:
        """Return 'note' or 'interval'."""
        return self._selection_mode

    def clear_interval_selection(self) -> None:
        """Return to note-selection mode, keep selected_index."""
        self._selection_mode = "note"
        self._selection_interval = None

    def get_selection_interval(self) -> Optional[Tuple[int, float, float]]:
        """
        Return (measure_index, beat_start_float, beat_end_float) if in interval mode,
        or None otherwise.

        Internally we store BeatTime, but the public API still exposes floats so
        existing callers (App, StaffView) keep working.
        """
        if self._selection_mode != "interval":
            return None
        if self._selection_interval is None:
            return None

        mi, bt_start, bt_end = self._selection_interval
        return mi, bt_start.to_float(), bt_end.to_float()

    def select_interval_for_index(self, index: int) -> Optional[Tuple[int, float, float]]:
        """
        Use the note at `index` to define an interval selection:
        its measure and beat range (start..end).

        Sets selection_mode to 'interval' and returns the interval as floats,
        while storing BeatTime internally.
        """
        if not self._notes_flat:
            return None
        if index < 0 or index >= len(self._notes_flat):
            return None

        mi, ni, _ = self._notes_flat[index]
        measure = self.score.measures[mi]

        # Compute beat start/end in floats
        beat_start = 0.0
        for j, n in enumerate(measure.notes):
            if j == ni:
                break
            beat_start += n.duration_beats
        beat_end = beat_start + measure.notes[ni].duration_beats

        # Store as BeatTime internally
        bt_start = BeatTime.from_float(beat_start)
        bt_end = BeatTime.from_float(beat_end)

        self.selected_index = index
        self._selection_mode = "interval"
        self._selection_interval = (mi, bt_start, bt_end)

        # Return floats for callers
        return mi, bt_start.to_float(), bt_end.to_float()


    def get_selected_note_indices(self) -> List[int]:
        """
        Return a list of flat note indices affected by the current selection.
        - note mode: [selected_index] or []
        - interval mode: all notes whose time range overlaps the interval
        """
        if not self._notes_flat:
            return []

        if self._selection_mode == "note":
            idx = self.get_selection_index()
            return [] if idx is None else [idx]

        if self._selection_interval is None:
            return []

        target_mi, bt_start, bt_end = self._selection_interval
        sel_start = bt_start.to_float()
        sel_end = bt_end.to_float()
        if sel_end <= sel_start:
            return []

        measure = self.score.measures[target_mi]
        beats: List[Tuple[float, float]] = []
        beat_pos = 0.0
        for n in measure.notes:
            start = beat_pos
            end = start + n.duration_beats
            beats.append((start, end))
            beat_pos = end

        indices: List[int] = []
        for flat_idx, (mi, ni, _note) in enumerate(self._notes_flat):
            if mi != target_mi:
                continue
            start, end = beats[ni]
            if end > sel_start and start < sel_end:
                indices.append(flat_idx)

        return indices


    def get_note_beat_range_from_flat_index(
        self, index: int
    ) -> Optional[Tuple[int, int, float, float]]:
        """
        Compute (measure_index, note_index_in_measure, beat_start, beat_end)
        for a given flat index, without changing selection mode.
        """
        if not self._notes_flat:
            return None
        if index < 0 or index >= len(self._notes_flat):
            return None

        mi, ni, _ = self._notes_flat[index]
        measure = self.score.measures[mi]

        beat_start = 0.0
        for j, n in enumerate(measure.notes):
            if j == ni:
                break
            beat_start += n.duration_beats
        beat_end = beat_start + measure.notes[ni].duration_beats

        return mi, ni, beat_start, beat_end

    # ----- selection API (note index) --------------------------

    def get_selection_index(self) -> Optional[int]:
        """Return the clamped selected index, or None if no notes."""
        if not self._notes_flat:
            return None
        idx = max(0, min(self.selected_index, len(self._notes_flat) - 1))
        return idx

    def set_selection_index(self, index: int) -> Optional[int]:
        """Set selection to a specific index (clamped). Returns the clamped value or None."""
        if not self._notes_flat:
            self.selected_index = 0
            return None
        n = len(self._notes_flat)
        self.selected_index = max(0, min(index, n - 1))
        # Switching back to note mode if we explicitly select a note
        if self._selection_mode == "interval":
            # you can choose to keep interval mode if you prefer; I reset to note
            self._selection_mode = "note"
            self._selection_interval = None
        return self.selected_index

    def move_selection(self, delta: int) -> Optional[int]:
        """Move selection by a relative delta. Returns new index or None."""
        if not self._notes_flat:
            return None
        return self.set_selection_index(self.selected_index + delta)

    # ----- editing API -----------------------------------------

    def transpose_selected(
        self,
        steps: int,
        *,
        transpose_pitch_func: Optional[Callable[[str, int], str]] = None,
    ) -> Optional[int]:
        """
        Transpose the currently selected *primary* note by `steps`.

        - If transpose_pitch_func is provided, it is called as:
          new_pitch = transpose_pitch_func(old_pitch, steps)
        - Returns the selection index after edit (or None if nothing selected).

        (For now, interval selection still only transposes the primary note.
         Later we can apply it to all get_selected_note_indices().)
        """
        idx = self.get_selection_index()
        if idx is None:
            return None

        mi, ni, note = self._notes_flat[idx]

        if transpose_pitch_func is not None:
            old_pitch = note.pitch
            note.pitch = transpose_pitch_func(old_pitch, steps)
        else:
            # No-op if no transpose function is given
            return idx

        # After editing the score, rebuild the flat list
        self._rebuild_flat()
        # Keep selection on the same logical index if possible
        if idx >= len(self._notes_flat):
            idx = len(self._notes_flat) - 1
        self.selected_index = idx
        return idx
# domain/notation.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Set

from engine.timebase import BeatTime
from domain.score import Score


class DurationValue(Enum):
    WHOLE = auto()
    HALF = auto()
    QUARTER = auto()
    EIGHTH = auto()
    SIXTEENTH = auto()
    THIRTY_SECOND = auto()
    # Extend later if needed


@dataclass
class NotatedDuration:
    """
    A purely notational duration (quarter, dotted-eighth, etc.).
    """
    base: DurationValue
    dots: int = 0  # 0 = plain, 1 = dotted, etc.


class NotationTie(Enum):
    NONE = auto()
    START = auto()
    STOP = auto()
    TIE_BOTH = auto()  # middle note in a tie chain


@dataclass
class NotatedAtom:
    """
    One visual note/rest on the staff.

    For now:
      - pitch: "C4", "REST", ...
      - beat_start: position within the measure
      - duration: notational duration (quarter, eighth, ...)
    """
    pitch: str
    measure_index: int
    beat_start: BeatTime
    duration: NotatedDuration
    tie: NotationTie = NotationTie.NONE

    voice: int = 0
    beam_group_id: Optional[int] = None
    slur_group_id: Optional[int] = None
    articulations: Set[str] = field(default_factory=set)


@dataclass
class NotatedMeasure:
    index: int
    time_signature: tuple[int, int]
    atoms: List[NotatedAtom] = field(default_factory=list)


@dataclass
class NotatedScore:
    title: str
    measures: List[NotatedMeasure]


# ---------- Simple mapping from beats -> notation (for now) ----------

def beats_to_notated_duration(
    duration_beats: float,
    time_signature: tuple[int, int],
) -> NotatedDuration:
    """
    Extremely naive mapping that assumes 4/4-like powers-of-two durations.

    This is *only* to get something consistent for our current nice demo scores.
    Later we'll replace this with proper quantization and dotted values.
    """
    eps = 1e-6

    if abs(duration_beats - 4.0) < eps:
        return NotatedDuration(DurationValue.WHOLE)
    if abs(duration_beats - 2.0) < eps:
        return NotatedDuration(DurationValue.HALF)
    if abs(duration_beats - 1.0) < eps:
        return NotatedDuration(DurationValue.QUARTER)
    if abs(duration_beats - 0.5) < eps:
        return NotatedDuration(DurationValue.EIGHTH)
    if abs(duration_beats - 0.25) < eps:
        return NotatedDuration(DurationValue.SIXTEENTH)

    # Fallback: treat as quarter for now
    return NotatedDuration(DurationValue.QUARTER)


def build_notated_score(score: Score) -> NotatedScore:
    """
    Build a NotatedScore from the current Score, assuming well-behaved durations.

    No beams/slurs/ties yet; just atoms with notational durations.
    """
    measures: list[NotatedMeasure] = []
    ts = score.time_signature if score.time_signature else (4, 4)

    for mi, measure in enumerate(score.measures):
        nm = NotatedMeasure(index=mi, time_signature=ts)
        beat_start_float = 0.0

        for note in measure.notes:
            duration_beats = note.duration_beats
            ndur = beats_to_notated_duration(duration_beats, ts)

            atom = NotatedAtom(
                pitch=note.pitch,
                measure_index=mi,
                beat_start=BeatTime.from_float(beat_start_float),
                duration=ndur,
                tie=NotationTie.NONE,
                voice=0,
                beam_group_id=None,
                slur_group_id=None,
            )
            nm.atoms.append(atom)

            beat_start_float += duration_beats

        measures.append(nm)

    return NotatedScore(
        title=getattr(score, "title", "") or "Untitled",
        measures=measures,
    )

def notated_duration_to_beats(
    ndur: NotatedDuration,
    time_signature: tuple[int, int],
) -> float:
    """
    Naive inverse of beats_to_notated_duration for 4/4-style scores.

    We assume:
      quarter note  -> 1.0 beat
      half          -> 2.0 beats
      whole         -> 4.0 beats
      eighth        -> 0.5 beats
      sixteenth     -> 0.25 beats

    Dots multiply by (1 + 1/2 + 1/4 + ...).
    """
    # Base durations in beats (relative to a quarter-note = 1.0)
    base_beats = {
        DurationValue.WHOLE: 4.0,
        DurationValue.HALF: 2.0,
        DurationValue.QUARTER: 1.0,
        DurationValue.EIGHTH: 0.5,
        DurationValue.SIXTEENTH: 0.25,
        DurationValue.THIRTY_SECOND: 0.125,
    }.get(ndur.base, 1.0)

    # Dot factor: e.g. 1 dot => 1 + 1/2 = 1.5
    factor = 1.0
    frac = 0.5
    for _ in range(ndur.dots):
        factor += frac
        frac *= 0.5

    return base_beats * factor
# score.py
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class Note:
    pitch: str
    duration_beats: float

@dataclass
class Measure:
    notes: List[Note]

@dataclass
class Score:
    title: str
    tempo_bpm: int
    time_signature: tuple[int, int]
    measures: List[Measure]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Score":
        measures = []
        for m in data["measures"]:
            notes = [Note(n["pitch"], n["duration_beats"]) for n in m["notes"]]
            measures.append(Measure(notes))
        return cls(
            title=data.get("title", "Untitled"),
            tempo_bpm=data.get("tempo_bpm", 80),
            time_signature=tuple(data.get("time_signature", [4, 4])),
            measures=measures,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "tempo_bpm": self.tempo_bpm,
            "time_signature": list(self.time_signature),
            "measures": [
                {"notes": [
                    {"pitch": n.pitch, "duration_beats": n.duration_beats}
                    for n in measure.notes
                ]}
                for measure in self.measures
            ],
        }

    def all_notes(self):
        for mi, measure in enumerate(self.measures):
            for ni, note in enumerate(measure.notes):
                yield mi, ni, note
 
    # def to_midi_clip(self) -> MidiClip:
    #     """
    #     Flatten this Score into a MidiClip:
    #     - events laid out sequentially in beats
    #     - clip starts at beat 0
    #     - clip length is the total duration of all notes

    #     This does NOT change the score; it's just a derived representation
    #     that the engine can use for DAW-like playback.
    #     """
    #     events: list[MidiEvent] = []
    #     current_beat = 0.0

    #     for measure in self.measures:
    #         for note in measure.notes:
    #             duration = note.duration_beats
    #             events.append(
    #                 MidiEvent(
    #                     start_beats=current_beat,
    #                     duration_beats=duration,
    #                     pitch=note.pitch,
    #                     velocity=100,
    #                 )
    #             )
    #             current_beat += duration

    #     length_beats = current_beat
    #     return MidiClip(
    #         start_beats=0.0,
    #         length_beats=length_beats,
    #         events=events,
    #     )
 
    def total_beats(self) -> float:
        total = 0.0
        for m in self.measures:
            for n in m.notes:
                total += n.duration_beats
        return total# domain/theory.py

from __future__ import annotations

from typing import Final

LETTER_ORDER: Final[list[str]] = ["C", "D", "E", "F", "G", "A", "B"]
MIN_DIATONIC_INDEX: Final[int] = LETTER_ORDER.index("E") + 7 * 4  # E4
MAX_DIATONIC_INDEX: Final[int] = LETTER_ORDER.index("F") + 7 * 5  # F5


def pitch_to_diatonic_index(pitch: str) -> int:
    """
    Map a pitch like 'C4', 'D5', 'REST' to a diatonic integer index.
    This is the same logic you currently have in App.pitch_to_diatonic_index.
    """
    up = pitch.upper()
    if up == "REST":
        return MIN_DIATONIC_INDEX

    i = 0
    while i < len(pitch) and not pitch[i].isdigit():
        i += 1
    name = pitch[:i]
    octave_str = pitch[i:] or "4"

    letter = name[0].upper()
    octave = int(octave_str)

    if letter not in LETTER_ORDER:
        return MIN_DIATONIC_INDEX

    return LETTER_ORDER.index(letter) + 7 * octave


def diatonic_index_to_pitch(index: int) -> str:
    """
    Inverse of pitch_to_diatonic_index (within the diatonic system).
    """
    octave, letter_idx = divmod(index, 7)
    letter = LETTER_ORDER[letter_idx]
    return f"{letter}{octave}"


def transpose_pitch_diatonic(pitch: str, steps: int) -> str:
    """
    Transpose a pitch by diatonic steps, clamped between MIN_DIATONIC_INDEX
    and MAX_DIATONIC_INDEX. Rests are preserved.
    """
    up = pitch.upper()
    if up == "REST":
        return pitch

    idx = pitch_to_diatonic_index(pitch)
    idx_new = idx + steps

    if idx_new < MIN_DIATONIC_INDEX:
        idx_new = MIN_DIATONIC_INDEX
    if idx_new > MAX_DIATONIC_INDEX:
        idx_new = MAX_DIATONIC_INDEX

    return diatonic_index_to_pitch(idx_new)
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
# maybe in ui/app.py or engine/io.py
import json
from pathlib import Path
from typing import Tuple

from domain.score import Score
from engine.project import Project


def load_project_or_score(path: str | Path) -> Tuple[Project, Score]:
    """
    - If JSON has 'tracks' → interpret as Project; derive Score from first MIDI clip's 'score' field.
    - Else → interpret as legacy Score JSON; wrap into a one-track Project.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # New project format
    if "tracks" in data:
        project = Project.from_dict(data)

        # Find first MIDI track & its first clip
        if not project.tracks:
            raise ValueError("Project has no tracks")

        midi_track = None
        for t in project.tracks:
            if t.track_type == Project.TrackType.MIDI if hasattr(Project, "TrackType") else True:
                midi_track = t
                break
        if midi_track is None:
            midi_track = project.tracks[0]

        if not midi_track.clips:
            raise ValueError("MIDI track has no clips")

        clip_dicts = data["tracks"][project.tracks.index(midi_track)]["clips"]
        first_clip_dict = clip_dicts[0]
        score_dict = first_clip_dict.get("score")
        if not score_dict:
            raise ValueError("Project clip has no embedded 'score'")

        score = Score.from_dict(score_dict)
        return project, score

    # Legacy score format: wrap into project
    else:
        score = Score.from_dict(data)
        project = Project.from_score(score, track_name=score.title or "Flute")
        return project, score

def save_project_to_json(path: str | Path, project: Project, score: Score) -> None:
    data = project.to_dict(score_for_first_midi_track=score)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
# metronome.py
import time
from typing import Callable, Optional
from engine.audio_engine import AudioEngine
from engine.timebase import beat_duration_ms

class Metronome:
    def __init__(self,
                 root,
                 audio: AudioEngine,
                 tempo_bpm: int = 80,
                 beats_per_bar: int = 4,
                 visual_callback: Optional[Callable[[bool], None]] = None):
        self.root = root
        self.audio = audio
        self.tempo_bpm = tempo_bpm
        self.beats_per_bar = beats_per_bar
        self.visual_callback = visual_callback

        self.is_running = False
        self.current_beat = 0  # 1..beats_per_bar
        self.last_beat_time_ms: Optional[int] = None

    def set_tempo(self, bpm: int):
        self.tempo_bpm = max(20, min(bpm, 300))

    def set_beats_per_bar(self, n: int):
        self.beats_per_bar = max(1, n)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.current_beat = 0
            self._schedule_next()

    def stop(self):
        self.is_running = False

    def _schedule_next(self):
        if not self.is_running:
            return

        self.current_beat = (self.current_beat % self.beats_per_bar) + 1
        strong = (self.current_beat == 1)

        now_ms = int(time.time() * 1000)
        self.last_beat_time_ms = now_ms

        if self.visual_callback:
            self.visual_callback(strong)

        # NEW: non-blocking trigger, mix with note
        self.audio.trigger_click(strong=strong)

        beat_interval_ms = beat_duration_ms(self.tempo_bpm)
        self.root.after(beat_interval_ms, self._schedule_next)

    def get_last_beat_info(self) -> tuple[int, Optional[int]]:
        """
        Returns (current_beat, last_beat_time_ms).
        current_beat is 1..beats_per_bar, or 0 if no beat yet.
        last_beat_time_ms is epoch milliseconds, or None if no beat yet.
        """
        return self.current_beat, self.last_beat_time_ms
# player.py
from __future__ import annotations

from typing import Callable, Optional, List, Tuple

from domain.score import Score
from engine.project import MidiClip
from engine.audio_engine import AudioEngine
from engine.transport import Transport


class PlaybackController:
    """
    Beat-based playback controller.

    - Reads events from a MidiClip.
    - Uses Transport.current_beats as the master musical clock.
    - Triggers AudioEngine.play_note for events whose start_beats are reached.
    - Keeps a flat note list for UI highlighting, 1:1 with events (for now).
    """

    def __init__(
        self,
        score: Score,
        audio: AudioEngine,
        transport: Transport,
        clip: MidiClip,
        update_ui: Callable[[int, list], None],
    ):
        self.score = score
        self.audio = audio
        self.transport = transport
        self.clip = clip
        self.update_ui = update_ui

        # Flat notes list for UI: (measure_index, note_index_in_measure, note_obj)
        self.notes_flat: List[Tuple[int, int, object]] = list(score.all_notes())

        self.is_playing: bool = False
        self.loop_enabled: bool = False

        # Loop is index-based for UI, but we also track it in beats for transport.
        self.loop_start_index: int = 0
        self.loop_end_index: int = max(0, len(self.notes_flat) - 1)
        self.loop_start_beats: float = 0.0
        self.loop_end_beats: float = 0.0

        # Playback state
        self._next_event_index: int = 0
        self._last_processed_beats: Optional[float] = None

        # Initialize loop region in both indices and beats
        self.set_loop_region(self.loop_start_index, self.loop_end_index)

    # ------------------------------------------------------------------
    # Score / clip reset
    # ------------------------------------------------------------------
    def reset_score(self, score: Score, clip: MidiClip) -> None:
        """
        Called when we load a new score.

        Keeps interface compatible for the rest of the app.
        """
        self.score = score
        self.clip = clip
        self.notes_flat = list(score.all_notes())

        # Reset playback state
        self.is_playing = False
        self._next_event_index = 0
        self._last_processed_beats = None

        # Rebuild default loop: whole song
        self.loop_start_index = 0
        self.loop_end_index = max(0, len(self.notes_flat) - 1)
        self.set_loop_region(self.loop_start_index, self.loop_end_index)

    # ------------------------------------------------------------------
    # Loop controls (still index-based on the UI side)
    # ------------------------------------------------------------------
    def set_loop_region(self, start_idx: int, end_idx: int) -> None:
        """
        Set loop region in terms of note indices, and recompute loop bounds in beats.
        """
        if not self.notes_flat or not self.clip or not self.clip.events:
            # No notes or no clip events → no meaningful loop; keep defaults.
            self.loop_start_index = 0
            self.loop_end_index = 0
            self.loop_start_beats = 0.0
            self.loop_end_beats = 0.0
            return

        n = len(self.notes_flat)
        self.loop_start_index = max(0, min(start_idx, n - 1))
        self.loop_end_index = max(self.loop_start_index, min(end_idx, n - 1))

        # --- Compute loop bounds in beats based on events ---
        evs = self.clip.events
        if evs:
            # Guard in case notes_flat and events diverge in size
            start_idx_clamped = max(0, min(self.loop_start_index, len(evs) - 1))
            end_idx_clamped = max(0, min(self.loop_end_index, len(evs) - 1))

            start_ev = evs[start_idx_clamped]
            end_ev = evs[end_idx_clamped]

            self.loop_start_beats = start_ev.start_beats
            # loop end beat is end-note start + its duration
            self.loop_end_beats = end_ev.start_beats + end_ev.duration_beats
        else:
            self.loop_start_beats = 0.0
            self.loop_end_beats = 0.0

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_enabled = enabled

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_event_index_for_beats(self, beats: float) -> int:
        """
        Find the first event whose start_beats >= beats.
        """
        events = self.clip.events if self.clip is not None else []
        i = 0
        n = len(events)
        while i < n and events[i].start_beats < beats:
            i += 1
        return i

    def _wrap_to_loop_start(self) -> None:
        """
        Wrap playback to the loop start index and reposition transport.
        """
        if not self.clip or not self.clip.events or not self.notes_flat:
            return

        start_idx = max(0, min(self.loop_start_index, len(self.clip.events) - 1))
        self._start_at_index(start_idx)

    # ------------------------------------------------------------------
    # Play / pause / stop
    # ------------------------------------------------------------------
    def play_from_beginning(self) -> None:
        """Start from beginning (or loop start if loop_enabled)."""
        if not self.notes_flat or not self.clip or not self.clip.events:
            return

        idx = self.loop_start_index if self.loop_enabled else 0
        self._start_at_index(idx)

    def play_from_index(self, index: int | None) -> None:
        if index is None or not self.clip or not self.clip.events:
            return
        idx = max(0, min(index, len(self.clip.events) - 1))
        self._start_at_index(idx)

    def _start_at_index(self, index: int) -> None:
        """
        Internal: set transport position & event pointer, then start playback.
        """
        if not self.clip or not self.clip.events:
            return

        events = self.clip.events
        index = max(0, min(index, len(events) - 1))
        self._next_event_index = index

        start_beat = events[index].start_beats
        self.transport.set_position_beats(start_beat)

        # IMPORTANT: initialize last_processed just *before* start_beat,
        # so the first tick will see the note in (last, current].
        self._last_processed_beats = start_beat - 1e-6

        self.transport.play()
        self.is_playing = True

    def play(self) -> None:
        """
        Backwards-compatible: same as play_from_beginning().
        """
        self.play_from_beginning()

    def pause(self) -> None:
        # We *don't* stop the transport; it's a global clock used by other stuff.
        self.is_playing = False

    def stop(self) -> None:
        self.is_playing = False
        self._next_event_index = 0
        self._last_processed_beats = None
        if self.notes_flat:
            self.update_ui(0, self.notes_flat)

    # ------------------------------------------------------------------
    # Beat-based processing (called from Session / App transport loop)
    # ------------------------------------------------------------------

    def _beats_for_index(self, idx: int) -> float:
        """
        Return the absolute beat position for the note at flat index `idx`.

        For now this is only used for debugging / future helpers.
        """
        if not self.notes_flat:
            return 0.0

        # Clamp index
        if idx <= 0:
            return 0.0
        if idx >= len(self.notes_flat):
            idx = len(self.notes_flat) - 1

        total = 0.0
        # accumulate durations of earlier notes
        for i in range(idx):
            _mi, _ni, note = self.notes_flat[i]
            total += note.duration_beats

        return total

    def process_tick(self) -> None:
        """
        Called regularly from Session.process_tick().

        Looks at transport.current_beats and triggers all events
        that start between last_processed_beats and current_beats.
        """
        if not self.is_playing:
            return
        if not self.clip or not self.clip.events or not self.notes_flat:
            return

        current_beats = self.transport.current_beats

        # Initialize last_processed_beats on first run
        if self._last_processed_beats is None:
            self._last_processed_beats = current_beats

        events = self.clip.events
        n = len(events)

        # If time went backwards (manual reposition or loop wrap),
        # rescan to find the appropriate event index.
        if current_beats < self._last_processed_beats:
            self._next_event_index = self._find_event_index_for_beats(current_beats)

        # DEBUG: you can comment this out once things are stable
        if 0 <= self._next_event_index < n:
            ev_debug = events[self._next_event_index]
            print(
                "tick: last=", self._last_processed_beats,
                "current=", current_beats,
                "next_idx=", self._next_event_index,
                "ev_start=", ev_debug.start_beats,
            )
        else:
            print(
                "tick: last=", self._last_processed_beats,
                "current=", current_beats,
                "next_idx=", self._next_event_index,
                "ev_start= <none>",
            )

        # ---- Trigger events whose start is in (last, current] ----
        while self._next_event_index < n:
            ev = events[self._next_event_index]
            start = ev.start_beats

            # Already beyond current beat → nothing else to trigger now
            if start > current_beats:
                break

            # Only trigger if it wasn't already passed on previous tick
            if start > self._last_processed_beats:
                idx = self._next_event_index
                self.update_ui(idx, self.notes_flat)
                duration_s = self._beats_to_seconds(ev.duration_beats)
                self.audio.play_note(ev.pitch, duration_s, volume=0.25)

            self._next_event_index += 1

        # After processing events up to current_beats:
        self._last_processed_beats = current_beats

        # If looping: wrap when transport passes loop_end_beats
        if self.loop_enabled:
            if current_beats >= self.loop_end_beats:
                self._wrap_to_loop_start()
                return

        # If not looping: stop at end of clip
        elif self._next_event_index >= n:
            self.is_playing = False

    def _beats_to_seconds(self, beats: float) -> float:
        beat_duration_s = 60.0 / max(1, self.score.tempo_bpm)
        return beats * beat_duration_s
# engine/project.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from domain.score import Score

def midi_clip_from_score(score: "Score",
                         start_beats: float = 0.0,
                         default_velocity: int = 100) -> "MidiClip":
    """
    Convert a Score into a flat MidiClip:
    - events laid out in time, sequentially
    - start_beats is the offset of the first event
    """
    total = score.total_beats()
    events: List[MidiEvent] = []

    t = start_beats
    for measure in score.measures:
        for note in measure.notes:
            events.append(
                MidiEvent(
                    start_beats=t,
                    duration_beats=note.duration_beats,
                    pitch=note.pitch,
                    velocity=default_velocity,
                )
            )
            t += note.duration_beats

    return MidiClip(
        start_beats=start_beats,
        length_beats=total,
        events=events,
    )


@dataclass
class Clip:
    """
    Base clip on the timeline.
    """
    start_beats: float
    length_beats: float


class TrackType(str, Enum):
    MIDI = "midi"
    AUDIO = "audio"

# --- MidiEvent -------------------------------------------------

@dataclass
class MidiEvent:
    start_beats: float
    duration_beats: float
    pitch: str
    velocity: int = 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_beats": self.start_beats,
            "duration_beats": self.duration_beats,
            "pitch": self.pitch,
            "velocity": self.velocity,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MidiEvent":
        return cls(
            start_beats=float(data["start_beats"]),
            duration_beats=float(data["duration_beats"]),
            pitch=str(data["pitch"]),
            velocity=int(data.get("velocity", 100)),
        )


# --- MidiClip --------------------------------------------------

@dataclass
class MidiClip:
    start_beats: float
    length_beats: float
    events: List[MidiEvent] = field(default_factory=list)

    # NOTE: we also allow embedding a score dict for now, instead of events-only.
    # The app still uses Score as the editable truth.
    def to_dict(self, score: Optional[Score] = None) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "type": "midi",
            "start_beats": self.start_beats,
            "length_beats": self.length_beats,
        }
        # For now: we persist the Score representation as ground truth.
        # Events are derivable and can be added later.
        if score is not None:
            d["score"] = score.to_dict()
        else:
            # fallback: emit events if we don't have a Score
            d["events"] = [ev.to_dict() for ev in self.events]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MidiClip":
        start_beats = float(data.get("start_beats", 0.0))
        length_beats = float(data.get("length_beats", 0.0))
        events_data = data.get("events", [])
        events = [MidiEvent.from_dict(e) for e in events_data]
        return cls(
            start_beats=start_beats,
            length_beats=length_beats,
            events=events,
        )


# --- Track -----------------------------------------------------

@dataclass
class Track:
    name: str
    track_type: TrackType
    clips: List[MidiClip] = field(default_factory=list)

    def to_dict(self, score_for_first_clip: Optional[Score] = None) -> Dict[str, Any]:
        clips_dicts: List[Dict[str, Any]] = []
        for i, clip in enumerate(self.clips):
            if i == 0 and score_for_first_clip is not None:
                clips_dicts.append(clip.to_dict(score_for_first_clip))
            else:
                clips_dicts.append(clip.to_dict())
        return {
            "name": self.name,
            "type": self.track_type.value,
            "clips": clips_dicts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Track":
        ttype = TrackType(data.get("type", "midi"))
        clips = [MidiClip.from_dict(c) for c in data.get("clips", [])]
        return cls(
            name=str(data.get("name", "Track 1")),
            track_type=ttype,
            clips=clips,
        )


# --- Project ---------------------------------------------------

@dataclass
class Project:
    tempo_bpm: int
    time_signature: Tuple[int, int]
    tracks: List[Track] = field(default_factory=list)

    def to_dict(self, score_for_first_midi_track: Optional[Score] = None) -> Dict[str, Any]:
        tracks_dicts: List[Dict[str, Any]] = []
        for t in self.tracks:
            # For now: only first MIDI track gets the Score embedded
            if (
                score_for_first_midi_track is not None
                and t.track_type == TrackType.MIDI
                and not tracks_dicts  # first track only
            ):
                tracks_dicts.append(t.to_dict(score_for_first_midi_track))
            else:
                tracks_dicts.append(t.to_dict())
        return {
            "tempo_bpm": self.tempo_bpm,
            "time_signature": list(self.time_signature),
            "tracks": tracks_dicts,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        tempo_bpm = int(data.get("tempo_bpm", 80))
        ts_list = data.get("time_signature", [4, 4])
        if len(ts_list) != 2:
            ts = (4, 4)
        else:
            ts = (int(ts_list[0]), int(ts_list[1]))
        tracks = [Track.from_dict(t) for t in data.get("tracks", [])]
        return cls(
            tempo_bpm=tempo_bpm,
            time_signature=ts,
            tracks=tracks,
        )

    @classmethod
    def from_score(cls, score: "Score", track_name: str = "Flute") -> "Project":
        clip = midi_clip_from_score(score, start_beats=0.0)
        track = Track(
            name=track_name or (score.title or "Track 1"),
            track_type=TrackType.MIDI,
            clips=[clip],
        )
        return cls(
            tempo_bpm=score.tempo_bpm,
            time_signature=score.time_signature,
            tracks=[track],
        )

# engine/session.py
from __future__ import annotations

from typing import Optional

from domain.score import Score
from domain.editor import EditorController
from engine.player import PlaybackController
from engine.timebase import compute_next_bar_start_time_ms
from engine.transport import Transport, Scheduler
from engine.metronome import Metronome
from domain.theory import transpose_pitch_diatonic
from engine.project import Clip, Project, Track, MidiClip


class Session:
    """
    Engine-level facade for the DAW state.

    Owns / coordinates:
      - Score + Editor
      - Transport + Scheduler
      - Metronome
      - PlaybackController
      - (Optionally) a Project with multiple tracks/clips
    """

    def __init__(
        self,
        score: Score,
        editor: EditorController,
        transport: Transport,
        scheduler: Scheduler,
        metronome: Optional[Metronome] = None,
        player: Optional[PlaybackController] = None,
        project: Optional[Project] = None,
    ) -> None:
        self.score = score
        self.editor = editor

        self.transport = transport
        self.scheduler = scheduler
        self.metronome: Optional[Metronome] = metronome
        self.player: Optional[PlaybackController] = player

        # Project / tracks / clips
        self.project: Optional[Project] = project
        self.active_track_index: int = 0
        self.active_clip_index: int = 0

        if self.project is not None:
            self._normalize_active_indices()
    # --- wiring -------------------------------------------------

    def attach_player(self, player: PlaybackController) -> None:
        self.player = player

    def attach_metronome(self, metronome: Metronome) -> None:
        self.metronome = metronome

    def has_notes(self) -> bool:
        return self.player is not None and bool(self.player.notes_flat)
    
        # --- project / tracks / clips -------------------------------

    def _normalize_active_indices(self) -> None:
        """
        Keep active_track_index / active_clip_index within bounds.
        For now we just clamp to 0 if the project is empty.
        """
        if self.project is None or not self.project.tracks:
            self.active_track_index = 0
            self.active_clip_index = 0
            return

        # Clamp track index
        if self.active_track_index < 0:
            self.active_track_index = 0
        if self.active_track_index >= len(self.project.tracks):
            self.active_track_index = len(self.project.tracks) - 1

        track = self.project.tracks[self.active_track_index]
        if not track.clips:
            self.active_clip_index = 0
            return

        # Clamp clip index
        if self.active_clip_index < 0:
            self.active_clip_index = 0
        if self.active_clip_index >= len(track.clips):
            self.active_clip_index = len(track.clips) - 1

    def set_project(
        self,
        project: Optional[Project],
        active_track_index: int = 0,
        active_clip_index: int = 0,
    ) -> None:
        """
        Replace the current Project and set active track/clip indices.

        For now this does NOT automatically change `score` / `editor` / `player`;
        App still manages those. Later we can make this choose the score/clip
        from the active track.
        """
        self.project = project
        self.active_track_index = active_track_index
        self.active_clip_index = active_clip_index
        if self.project is not None:
            self._normalize_active_indices()

    def set_active_track(self, idx: int) -> None:
        self.active_track_index = idx
        self._normalize_active_indices()

    def set_active_clip(self, idx: int) -> None:
        self.active_clip_index = idx
        self._normalize_active_indices()

    def get_active_track(self) -> Optional[Track]:
        if self.project is None or not self.project.tracks:
            return None
        self._normalize_active_indices()
        return self.project.tracks[self.active_track_index]

    def get_active_clip(self) -> Optional[Clip]:
        """
        Return the currently active Clip (may be MidiClip or another Clip subclass).
        """
        track = self.get_active_track()
        if track is None or not track.clips:
            return None
        self._normalize_active_indices()
        return track.clips[self.active_clip_index]

    def get_active_midi_clip(self) -> Optional[MidiClip]:
        """
        Convenience for the common '1 MIDI track' case.
        Returns None if the active track is not MIDI or has no MidiClip.
        """
        clip = self.get_active_clip()
        if isinstance(clip, MidiClip):
            return clip
        return None


    # --- global time / tempo -----------------------------------

    def compute_next_bar_delay_ms(self, now_ms: int) -> Optional[int]:
        """
        Compute how many milliseconds to wait until the start of the next bar,
        based on the metronome's last beat info and the current tempo / time signature.

        Returns:
          - delay in ms (>= 0) if we can align to the next bar
          - None if we don't have enough info (no metronome, not running, etc.)
        """
        if self.metronome is None or not self.metronome.is_running:
            return None

        beats_per_bar = self.score.time_signature[0]
        if beats_per_bar <= 0:
            return None

        current_beat, last_beat_time_ms = self.metronome.get_last_beat_info()
        if last_beat_time_ms is None:
            return None

        target_time_ms = compute_next_bar_start_time_ms(
            tempo_bpm=self.score.tempo_bpm,
            beats_per_bar=beats_per_bar,
            current_beat_in_bar=current_beat,
            last_beat_time_ms=last_beat_time_ms,
            now_ms=now_ms,
        )
        delay_ms = max(0, target_time_ms - now_ms)
        return delay_ms


    def process_tick(self, dt_seconds: float) -> None:
        """
        Advance musical time and let scheduled engine callbacks fire.
        This should be called regularly by the UI (e.g. every 20ms).
        """
        # 1) advance musical time
        self.transport.tick(dt_seconds)

        # 2) trigger any scheduled musical events
        self.scheduler.process()

        # 3) let the playback controller react to the new time
        if self.player is not None:
            self.player.process_tick()

    def set_tempo(self, bpm: int) -> None:
        """
        Set score tempo and propagate to transport + metronome.
        """
        self.score.tempo_bpm = bpm
        self.transport.set_tempo(bpm)
        if self.metronome is not None:
            self.metronome.set_tempo(bpm)

    def set_time_signature(self, ts: tuple[int, int]) -> None:
        """
        Set score time signature and propagate to transport + metronome.
        """
        self.score.time_signature = ts
        self.transport.set_time_signature(ts)
        if self.metronome is not None:
            self.metronome.set_beats_per_bar(ts[0])

    # --- loop management ----------------------------------------

    def initialize_loop_region(self) -> None:
        """
        Default loop: the whole song (all notes) if any.
        """
        if self.player is None or not self.player.notes_flat:
            return

        self.loop_start_index = 0
        self.loop_end_index = len(self.player.notes_flat) - 1
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_in_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_start_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_end_index = self.loop_start_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_out_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_end_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_start_index = self.loop_end_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_enabled(self, enabled: bool) -> None:
        if self.player is None:
            return
        self.player.set_loop_enabled(enabled)

    # --- playback controls --------------------------------------

    def play_from_beginning(self) -> None:
        if self.player is None:
            return
        self.player.play_from_beginning()

    def play_from_selection(self) -> None:
        if not self.has_notes():
            return

        idx = self.editor.get_selection_index()
        if idx is None:
            return

        assert self.player is not None
        self.player.play_from_index(idx)

    def pause(self) -> None:
        if self.player is None:
            return
        self.player.pause()

    def stop(self) -> None:
        if self.player is None:
            return
        self.player.stop()
        # Reset selection to the first note (if any)
        self.editor.set_selection_index(0)

    # --- selection / editing ------------------------------------

    def move_selection(self, delta: int) -> Optional[int]:
        """
        Move note selection by +1 / -1, etc.
        Returns the new index or None if it did not change.
        """
        if not self.has_notes():
            return None

        new_idx = self.editor.move_selection(delta)
        return new_idx

    def transpose_selected(self, delta_steps: int) -> Optional[int]:
        """
        Transpose the currently selected note diatonically.
        Returns the new selected index, or None if nothing changed.

        This mutates the underlying Score via EditorController.
        """
        if not self.has_notes():
            return None

        # Assumes EditorController.transpose_selected(delta, transpose_pitch_func=...)
        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=transpose_pitch_diatonic,
        )
        return new_idx

    def sync_active_midi_clip_from_score(self) -> None:
        """
        Sync the pitches in the active MidiClip from the current Score/editor.

        Assumes:
          - editor._notes_flat and clip.events correspond 1:1 in order.
        """
        clip = self.get_active_midi_clip()
        if clip is None:
            return

        flat = self.editor.get_flat_notes()
        events = clip.events

        n = min(len(flat), len(events))
        for i in range(n):
            _mi, _ni, note = flat[i]
            events[i].pitch = note.pitch


    # --- interval selection -------------------------------------

    def select_interval_for_current_note(self) -> bool:
        """
        Use the currently selected note as an interval selection.

        Returns True if an interval was selected, False otherwise.
        """
        idx = self.editor.get_selection_index()
        if idx is None:
            return False

        interval = self.editor.select_interval_for_index(idx)
        return interval is not None

    def clear_interval_selection(self) -> None:
        self.editor.clear_interval_selection()
# engine/timebase.py
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Tuple


@dataclass(frozen=True)
class BeatTime:
    """
    Simple wrapper around a 'beat index from zero' as a Fraction.

    For now we mostly use floats in the engine, but we can convert
    back and forth as needed. This is our future hook for precise
    PPQ-style timing.
    """
    beats: Fraction

    @classmethod
    def from_float(cls, value: float, max_denominator: int = 16) -> "BeatTime":
        # You can tweak max_denominator if you want more granularity
        return cls(Fraction(value).limit_denominator(max_denominator))

    def to_float(self) -> float:
        return float(self.beats)


def beat_label_from_zero_based(beat_zero_based: float) -> str:
    """
    Turn a zero-based beat index into a nice human-readable label:

    0.0   -> "1"
    0.5   -> "1 1/2"
    1.0   -> "2"
    2.25  -> "3 1/4"
    etc.

    This is basically what your App._beat_to_fraction_str did, but
    centralized here so everything uses the same logic.
    """
    bt = BeatTime.from_float(beat_zero_based, max_denominator=16)
    frac = bt.beats

    # Separate integer + fractional part
    integer = frac.numerator // frac.denominator
    remainder = Fraction(frac.numerator % frac.denominator, frac.denominator)

    # Human beats are 1-based, internal representation is 0-based
    label_int = integer + 1

    if remainder == 0:
        return str(label_int)
    else:
        return f"{label_int} {remainder.numerator}/{remainder.denominator}"


def beat_interval_to_floats(start_zero_based: float, end_zero_based: float) -> Tuple[float, float]:
    """
    Helper in case we later store intervals as BeatTime/Fraction but
    the UI still wants floats. Right now this is trivial, but it gives
    us a single place to adjust once we go all-in on BeatTime.
    """
    return float(start_zero_based), float(end_zero_based)

# engine/timebase.py

def beat_duration_ms(tempo_bpm: int) -> int:
    """
    Duration of one beat, in milliseconds, for a given tempo.
    """
    if tempo_bpm <= 0:
        return 0
    return int(60000 / tempo_bpm)


def compute_next_bar_start_time_ms(
    tempo_bpm: int,
    beats_per_bar: int,
    current_beat_in_bar: int,
    last_beat_time_ms: int | None,
    now_ms: int,
) -> int:
    """
    Given the tempo, beats per bar, and the last beat info from the metronome,
    compute an absolute target time (ms since epoch) for the NEXT bar's beat 1.

    - current_beat_in_bar is usually 1-based (1..beats_per_bar).
    - last_beat_time_ms is the timestamp when current_beat_in_bar occurred.
    """
    if beats_per_bar <= 0:
        return now_ms

    beat_ms = beat_duration_ms(tempo_bpm)
    if beat_ms <= 0:
        return now_ms

    # If we never had a beat yet, just wait one full bar from now
    if current_beat_in_bar == 0 or last_beat_time_ms is None:
        beats_remaining = beats_per_bar
        return now_ms + beats_remaining * beat_ms

    # Example: on beat 3 of 4 → remaining = (4 - 3 + 1) = 2 beats
    beats_remaining = (beats_per_bar - current_beat_in_bar + 1)
    return last_beat_time_ms + beats_remaining * beat_ms
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple


@dataclass
class Transport:
    """
    Central musical clock, in beats.

    For now it's a simple 'always running' clock driven by the UI
    (App → Session.process_tick → Transport.tick).

    Responsibilities:
      - Keep track of current position in beats.
      - Advance time according to tempo (BPM).
      - (Optionally) wrap inside a loop range [loop_start, loop_end).

    Note:
      Loop fields are currently not wired to the rest of the engine; the
      main loop semantics live in PlaybackController. These fields give us
      a place to move that logic in the future.
    """

    tempo_bpm: int
    time_signature: tuple[int, int]

    current_beats: float = 0.0
    playing: bool = True  # global clock on/off

    loop_enabled: bool = False
    loop_start: float = 0.0
    loop_end: float = 0.0

    # ---------------- basic control ----------------

    def set_tempo(self, bpm: int) -> None:
        """Set tempo in BPM (clamped to >= 1)."""
        self.tempo_bpm = max(1, int(bpm))

    def set_time_signature(self, ts: tuple[int, int]) -> None:
        """
        Set time signature as (numerator, denominator), e.g., (4, 4) for 4/4.
        """
        self.time_signature = ts

    def set_position_beats(self, beats: float) -> None:
        """Set the current position in beats (>= 0)."""
        self.current_beats = max(0.0, float(beats))

    def play(self) -> None:
        """Turn the global clock on."""
        self.playing = True

    def stop(self) -> None:
        """Turn the global clock off (time no longer advances in tick())."""
        self.playing = False

    # ---------------- derived quantities ----------------

    @property
    def beats_per_second(self) -> float:
        """Tempo as beats per second."""
        return self.tempo_bpm / 60.0 if self.tempo_bpm > 0 else 0.0

    @property
    def seconds_per_beat(self) -> float:
        """Inverse of beats_per_second."""
        return 1.0 / self.beats_per_second if self.beats_per_second > 0 else 0.0

    def get_bar_and_beat(self) -> Tuple[int, float]:
        """
        Return (bar_index, beat_in_bar) based on current_beats and time_signature.

        Example in 4/4:
          current_beats = 0.0 → (0, 0.0)
          current_beats = 4.0 → (1, 0.0)
          current_beats = 5.5 → (1, 1.5)
        """
        beats_per_bar = self.time_signature[0] if self.time_signature else 4
        if beats_per_bar <= 0:
            return 0, self.current_beats

        bar_index = int(self.current_beats // beats_per_bar)
        beat_in_bar = self.current_beats - bar_index * beats_per_bar
        return bar_index, beat_in_bar

    # ---------------- main time update ----------------

    def tick(self, dt_seconds: float) -> None:
        """
        Advance the musical time by dt_seconds, according to tempo.

        Called regularly from Session.process_tick().
        """
        if not self.playing or self.tempo_bpm <= 0:
            return

        self.current_beats += self.beats_per_second * dt_seconds

        # Optional simple loop support (currently not used by PlaybackController).
        if self.loop_enabled and self.loop_end > self.loop_start:
            total = self.loop_end - self.loop_start
            if total > 0 and self.current_beats >= self.loop_end:
                # wrap around within the loop range
                delta = self.current_beats - self.loop_start
                self.current_beats = self.loop_start + (delta % total)


class Scheduler:
    """
    Tiny beat-based scheduler: run callbacks once when transport
    reaches or passes a given beat.

    One-shot: events are removed after they fire.
    """

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._events: List[Tuple[float, Callable[[], None]]] = []

    def schedule_at(self, beat: float, callback: Callable[[], None]) -> None:
        """
        Schedule a callback to run when transport.current_beats >= beat.
        """
        self._events.append((float(beat), callback))
        # keep events ordered by beat for simpler processing
        self._events.sort(key=lambda e: e[0])

    def clear(self) -> None:
        """Remove all scheduled callbacks."""
        self._events.clear()

    def process(self) -> None:
        """
        Check current_beats and run any due callbacks.
        Called regularly from Session.process_tick().
        """
        if not self._events:
            return

        now_beats = self.transport.current_beats
        to_run: List[Tuple[float, Callable[[], None]]] = []
        remaining: List[Tuple[float, Callable[[], None]]] = []

        for beat, cb in self._events:
            if beat <= now_beats:
                to_run.append((beat, cb))
            else:
                remaining.append((beat, cb))

        self._events = remaining

        for _beat, cb in to_run:
            cb()
# main.py
from ui.app import App


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
# notation/drawing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Literal

import tkinter as tk

from notation.style_config import StyleConfig


StemDirection = Literal["up", "down"]


@dataclass
class NoteDrawingContext:
    """
    Lightweight container with all info drawing helpers need.

    Keeps the primitives decoupled from StaffView internals.
    """
    canvas: tk.Canvas
    style: StyleConfig
    line_spacing: float
    middle_line_y: float  # y position of the middle staff line


def draw_notehead(
    ctx: NoteDrawingContext,
    x: float,
    y: float,
    *,
    filled: bool,
    highlighted: bool,
) -> None:
    """
    Draw an oval notehead at (x, y). For now, we use simple ellipses;
    this could be replaced by a slanted polygon later.
    """
    cfg = ctx.style

    if highlighted:
        fill_color = cfg.fill_highlight
    else:
        fill_color = cfg.fill_quarter_and_shorter if filled else cfg.fill_half_and_whole

    ctx.canvas.create_oval(
        x - cfg.note_radius_x,
        y - cfg.note_radius_y,
        x + cfg.note_radius_x,
        y + cfg.note_radius_y,
        fill=fill_color,
        outline=cfg.outline,
        width=1.2,
    )


def draw_stem(
    ctx: NoteDrawingContext,
    x: float,
    y: float,
    direction: StemDirection,
) -> Tuple[float, float]:
    """
    Draw a vertical stem attached to the notehead at (x, y).

    Returns (x_tip, y_tip) where the stem ends, so beams can connect there.
    """
    cfg = ctx.style

    # Attach stems slightly to the right or left side of the notehead.
    if direction == "up":
        x_stem = x + cfg.note_radius_x
        y_base = y
        y_tip = y_base - cfg.stem_length
    else:  # "down"
        x_stem = x - cfg.note_radius_x
        y_base = y
        y_tip = y_base + cfg.stem_length

    ctx.canvas.create_line(
        x_stem,
        y_base,
        x_stem,
        y_tip,
        width=cfg.stem_width,
        fill=cfg.outline,
    )

    return x_stem, y_tip


def draw_beam_group(
    ctx: NoteDrawingContext,
    stem_tips: List[Tuple[float, float]],
    direction: StemDirection,
    beams: int,
) -> None:
    """
    Draw simple horizontal/slanted beams connecting the given stem tips.

    - `stem_tips` should be in visual order (left to right).
    - `beams` is the number of parallel beams to draw (1 for 8th, 2 for 16th).
    """
    if beams <= 0 or len(stem_tips) < 2:
        return

    cfg = ctx.style

    # We'll connect only the first and last stem tip with a straight line,
    # then draw additional beams offset by beam_spacing.
    x0, y0 = stem_tips[0]
    x1, y1 = stem_tips[-1]

    # Direction-based offset: for "up" stems beams go slightly below the tip,
    # for "down" stems they go slightly above.
    sign = 1.0 if direction == "down" else -1.0

    for i in range(beams):
        offset = sign * i * cfg.beam_spacing
        ctx.canvas.create_line(
            x0,
            y0 + offset,
            x1,
            y1 + offset,
            width=cfg.beam_thickness,
            fill=cfg.fill_quarter_and_shorter,
            capstyle=tk.PROJECTING,
        )
        
def draw_treble_clef(
    ctx: NoteDrawingContext,
    x: float,
    top_line_y: float,
    line_spacing: float,
) -> None:
    """
    Draw a simple treble clef at the left of the staff.

    For now we use the Unicode 𝄞 glyph; later this can be replaced by
    a custom vector path or an image for more consistent rendering.
    """
    # Vertical center: around lines 2–3
    y_center = top_line_y + 2 * line_spacing

    # Font size scaled to staff size
    font_size = int(line_spacing * 3.0)
    if font_size < 10:
        font_size = 10

    ctx.canvas.create_text(
        x,
        y_center,
        text="𝄞",
        font=("DejaVu Sans", font_size),
        fill=ctx.style.outline,
    )

def draw_time_signature(
    ctx: NoteDrawingContext,
    x: float,
    top_line_y: float,
    line_spacing: float,
    numerator: int,
    denominator: int,
) -> None:
    """
    Draw a simple numeric time signature (e.g. 4/4) just to the right
    of the clef, stacked vertically.
    """
    # Place numerator around line 2, denominator around line 4.
    y_num = top_line_y + 1.2 * line_spacing
    y_den = top_line_y + 2.8 * line_spacing

    font_size = int(line_spacing * 1.8)
    if font_size < 8:
        font_size = 8

    font = ("DejaVu Sans", font_size)

    ctx.canvas.create_text(
        x,
        y_num,
        text=str(numerator),
        font=font,
        fill=ctx.style.outline,
    )
    ctx.canvas.create_text(
        x,
        y_den,
        text=str(denominator),
        font=font,
        fill=ctx.style.outline,
    )
# notation/formatting.py
from __future__ import annotations

from typing import Literal

DurationKind = Literal["whole", "half", "quarter", "eighth", "sixteenth"]


def duration_kind_from_beats(beats: float) -> DurationKind:
    """
    Classify duration (in beats) into a coarse note type for drawing.

    Assumes 4/4 and clean powers of two:
      4.0   -> "whole"
      2.0   -> "half"
      1.0   -> "quarter"
      0.5   -> "eighth"
      0.25  -> "sixteenth"

    Fallback: treat as "quarter" for drawing purposes.
    """
    eps = 0.01
    if abs(beats - 4.0) < eps:
        return "whole"
    if abs(beats - 2.0) < eps:
        return "half"
    if abs(beats - 1.0) < eps:
        return "quarter"
    if abs(beats - 0.5) < eps:
        return "eighth"
    if abs(beats - 0.25) < eps:
        return "sixteenth"
    return "quarter"


def is_filled_notehead(kind: DurationKind) -> bool:
    """
    Whole/half are hollow, quarter and shorter are filled.
    """
    return kind not in ("whole", "half")


def beams_for_kind(kind: DurationKind) -> int:
    """
    Number of beams to draw for this duration.
    (For now, just 8th and 16th notes.)
    """
    if kind == "eighth":
        return 1
    if kind == "sixteenth":
        return 2
    return 0


def is_beamable(kind: DurationKind) -> bool:
    """
    Whether this duration should be part of a beam group.
    """
    return beams_for_kind(kind) > 0
# notation/style_config.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StyleConfig:
    """
    Central configuration for staff drawing styles.
    """
    # Notehead geometry
    note_radius_x: float = 6.0
    note_radius_y: float = 4.0

    # Stems
    stem_length: float = 36.0
    stem_width: float = 1.4

    # Beams
    beam_thickness: float = 3.0
    beam_spacing: float = 5.0  # distance between multiple beams (16th, 32nd, ...)

    # Colors
    fill_quarter_and_shorter: str = "black"
    fill_half_and_whole: str = "white"
    fill_highlight: str = "deepskyblue"
    outline: str = "black"

    # Staff / grid strokes
    staff_line_width: float = 1.2
    barline_width: float = 1.2
    beat_grid_width: float = 1.0

    staff_line_color: str = "black"
    barline_color: str = "#444444"
    beat_grid_color: str = "#bbbbbb"

    selection_fill: str = "#ffd8d8"

    # NEW: space reserved for clef + key + time signature
    info_region_width: float = 90.0
# app.py
from __future__ import annotations

import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable

from domain.score import Score
from engine.audio_engine import AudioEngine
from engine.player import PlaybackController
from engine.metronome import Metronome
from ui.widgets import Widgets
from domain.editor import EditorController
from engine.timebase import beat_label_from_zero_based
from engine.project import Project, Track
from engine.transport import Transport, Scheduler
from engine.io import load_project_or_score, save_project_to_json  # or adjust path
from engine.session import Session
from domain.theory import transpose_pitch_diatonic

if TYPE_CHECKING:
    # for type checkers only; avoids circular import at runtime
    from widgets import Widgets as WidgetsType


def load_score_from_json(path: str) -> Score:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Score.from_dict(data)


def save_score_to_json(score: Score, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score.to_dict(), f, indent=2)


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Flute Practice Prototype")

                # Core state
        self.score: Score = self._make_demo_score()
        self.project: Project | None = None
        self.main_track: Track | None = None
        self.main_clip = None

        # Core engine objects
        self.transport = Transport(
            tempo_bpm=self.score.tempo_bpm,
            time_signature=self.score.time_signature,
        )
        self.scheduler = Scheduler(self.transport)
        self.audio = AudioEngine()
        self.player: PlaybackController | None = None
        self.metronome: Metronome | None = None

        self.editor = EditorController(self.score)


        # Build project based on initial score

        # Engine facade: now knows about transport/scheduler
        self.session = Session(
            score=self.score,
            editor=self.editor,
            transport=self.transport,
            scheduler=self.scheduler,
        )
        # Inform session about the project
        self._build_project_from_score()
        self.session.set_project(self.project)

        self.on_toggle_stick_to_bar = False
        # UI
        self.widgets: WidgetsType = Widgets(self.root, self)

        # Engines (metronome + player)
        self._init_engines()
        self.transport.play()

        # Key bindings
        self.root.bind_all("<Key>", self.on_key)
        # Initial UI sync
        self._start_transport_loop()
        self.update_ui(0)

    # ====== Setup helpers ======================================

    def _apply_loaded_score_and_project(self,
                                        score: Score,
                                        project: Project | None) -> None:
        """
        Central place to update app state after loading either:
        - a legacy Score-only file, or
        - a full Project+Score file.
        """
        # If no project provided, wrap score into a simple one-track project
        if project is None:
            project = Project.from_score(score, track_name=score.title or "Flute")

        self.project = project
        self.score = score

        # Rebuild project/from score (main_clip etc.)
        self._build_project_from_score(self.score)

        # Sync the session with the loaded project
        self.session.set_project(self.project)
        # Editor + widgets
        
        self.editor.set_score(self.score)
        self.session.score = self.score
        self.widgets.set_score(self.editor.score)
        self.widgets.tempo_var.set(str(self.score.tempo_bpm))
        
        # Transport/Metronome
        if self.transport is not None:
            self.transport.set_tempo(self.score.tempo_bpm)
            self.transport.set_time_signature(self.score.time_signature)
            self.transport.set_position_beats(0.0)

        if self.metronome is not None:
            self.metronome.set_tempo(self.score.tempo_bpm)
            self.metronome.set_beats_per_bar(self.score.time_signature[0])
       
        # Player
        if self.player is not None:
            self.player.reset_score(self.score, self.main_clip)
            self.player.notes_flat = self.editor.get_flat_notes()

            # Re-attach to session & reset loop
            self.session.score = self.score
            self.session.attach_player(self.player)
            self.session.initialize_loop_region()
        # UI selection & repaint
        self.editor.set_selection_index(0)
        self.update_ui(0)

    def _build_project_from_score(self) -> None:
        """
        Build a Project with a single MIDI track and a single MidiClip
        derived from self.score.

        For now this is purely "engine-side": the UI and playback still
        use Score as before. Later, playback/transport will read from
        Project/Track/Clip.
        """
        track_name = getattr(self.score, "title", "") or "Track 1"

        # Wrap current score into a one-track, one-clip Project
        self.project = Project.from_score(self.score, track_name=track_name)

        # Cache main_track / main_clip for convenience
        if self.project.tracks:
            self.main_track = self.project.tracks[0]
            if self.main_track.clips:
                self.main_clip = self.main_track.clips[0]
            else:
                self.main_clip = None
        else:
            self.main_track = None
            self.main_clip = None
            
        # NEW: inform session (if it already exists)
        if hasattr(self, "session"):
            self.session.set_project(self.project)

    def _make_demo_score(self) -> Score:
        data = {
            "title": "Simple Flute Tune",
            "tempo_bpm": 80,
            "time_signature": [4, 4],
            "measures": [
                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
                                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
                           {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
                                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
            ],
        }
        return Score.from_dict(data)

    def _init_engines(self) -> None:
        # Metronome
        beats_per_bar = self.score.time_signature[0]
        self.metronome = Metronome(
            self.root,
            self.audio,
            tempo_bpm=self.score.tempo_bpm,
            beats_per_bar=beats_per_bar,
            visual_callback=self.widgets.metro_visual,
        )

        # Player (beat-based)
        self.player = PlaybackController(
            self.score,
            self.audio,
            self.transport,
            self.main_clip,
            self._player_update_callback,
        )

        # NEW: connect both to Session
        self.session.attach_metronome(self.metronome)
        self.session.attach_player(self.player)
        self.session.initialize_loop_region()

        # Staff initial score
        self.widgets.set_score(self.editor.score)
        
        
        

    # ====== Pitch and Beat helpers (diatonic, clamped) ==================

    def _beat_to_fraction_str(self, beat_zero_based: float) -> str:
       return beat_label_from_zero_based(beat_zero_based)

    
    # ====== UI update glue =====================================

    def _player_update_callback(self, current_idx, _notes_flat) -> None:
        """Called by PlaybackController when playback advances."""
        self.editor.set_selection_index(current_idx)
        self.update_ui(current_idx)
    
    def _update_status_from_index(self, idx: int) -> None:
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_status("No notes in score")
            return

        mode = self.editor.get_selection_mode()
        # If we're in interval mode, use the stored interval
        if mode == "interval":
            interval = self.editor.get_selection_interval()
            if interval is not None:
                mi, beat_start, beat_end = interval
                beat_start_str = self._beat_to_fraction_str(beat_start)
                beat_end_str = self._beat_to_fraction_str(beat_end)

                # Overlay
                self.widgets.set_selection_region(mi, beat_start, beat_end)

                # Count how many notes are inside
                selected_indices = self.editor.get_selected_note_indices()
                count = len(selected_indices)
                self.widgets.set_status(
                    f"Interval: measure {mi + 1}, beats {beat_start_str} → {beat_end_str}, {count} note(s)"
                )
                return
            # fall through to note mode if interval is None

        # Default: note mode (or fallback)
        note_info = self.editor.get_note_beat_range_from_flat_index(idx)
        if note_info is None:
            self.widgets.set_status("No notes in score")
            return

        mi, ni, beat_start, beat_end = note_info
        beat_start_str = self._beat_to_fraction_str(beat_start)
        beat_end_str = self._beat_to_fraction_str(beat_end)

        # Overlay uses the single-note interval
        self.widgets.set_selection_region(mi, beat_start, beat_end)

        # Get the actual Note object for the pitch
        _mi_flat, _ni_flat, note = self.player.notes_flat[idx]
        self.widgets.set_status(
            f"Measure {mi + 1}, note {ni + 1}, beats {beat_start_str} → {beat_end_str}, pitch {note.pitch}"
        )


    def update_ui(self, current_idx: int | None = None) -> None:
        """Refresh text label, staff highlight, status bar."""
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_note_list("No notes")
            self.widgets.highlight_note(-1)
            self.widgets.set_status("No notes in score")
            return

        # Sync selection with editor if an explicit index came from playback
        if current_idx is not None:
            self.editor.set_selection_index(current_idx)

        idx = self.editor.get_selection_index()
        if idx is None:
            self.widgets.set_note_list("No notes")
            self.widgets.highlight_note(-1)
            self.widgets.set_status("No notes in score")
            return        

        parts: list[str] = []
        for i, (_, _, note) in enumerate(self.player.notes_flat):
            parts.append(f"[{note.pitch}]" if i == idx else note.pitch)
        self.widgets.set_note_list(" ".join(parts))
        self.widgets.highlight_note(idx)
        self.widgets.scroll_to_note_index(idx)
        self._update_status_from_index(idx)

    # ====== Menu / file actions ================================
    def on_open_project(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            project, score = load_project_or_score(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")
            return

        self._apply_loaded_score_and_project(score, project)
    
    def on_open(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            new_score = load_score_from_json(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load score:\n{e}")
            return

        # No project in this case → None
        self._apply_loaded_score_and_project(new_score, project=None)

    def on_save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            # Ensure project reflects current score
            self.project = Project.from_score(self.score, track_name="Flute")
            save_project_to_json(path, self.project, self.score)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save project:\n{e}")

    def on_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_score_to_json(self.score, path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save score:\n{e}")


    def on_quit(self) -> None:
        self.root.quit()


    # ====== Metronome / tempo ==================================

    def on_toggle_metronome(self) -> None:
        if self.metronome is None:
            return
        if self.widgets.metro_on_var.get():
            self.metronome.set_tempo(self.score.tempo_bpm)
            self.metronome.set_beats_per_bar(self.score.time_signature[0])
            self.metronome.start()
        else:
            self.metronome.stop()

    def on_tempo_change(self, raw_value: str) -> None:
        try:
            bpm = int(raw_value)
        except ValueError:
            return

        bpm = max(20, min(bpm, 300))
        # Let the session propagate to score + transport + metronome
        self.session.set_tempo(bpm)

    # ====== Transport controls =================================
   
    def _start_transport_loop(self) -> None:
        """
        Start a periodic Tk timer that advances the Transport
        and processes scheduled events.
        """
        import time  # you probably already import time at top; if so, skip this

        self._last_transport_time = time.perf_counter()
        self._transport_tick()
        
        
    def _transport_tick(self) -> None:
        now = time.perf_counter()
        last = getattr(self, "_last_transport_time", now)
        dt = now - last
        self._last_transport_time = now

        # Now session owns the engine time progression
        self.session.process_tick(dt)

        self.root.after(20, self._transport_tick)

   
    def select_interval_for_current_note(self) -> None:
        """
        Use the currently selected note as an interval selection
        (its beat range in its measure).
        """
        changed = self.session.select_interval_for_current_note()
        if changed:
            self.update_ui()

    def clear_interval_selection(self) -> None:
        """
        Return to note-selection mode (keep current selected note).
        """
        self.session.clear_interval_selection()
        self.update_ui()

   
    def on_start(self) -> None:
        if not self.session.has_notes():
            return

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(self.session.play_from_beginning)
        else:
            self.session.play_from_beginning()

    def on_play_from_selected(self) -> None:
        if not self.session.has_notes():
            return

        def _do():
            self.session.play_from_selection()

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(_do)
        else:
            _do()

    def on_pause(self) -> None:
        self.session.pause()

    def on_stop(self) -> None:
        self.session.stop()
        # Selection is reset by Session.stop; just refresh UI
        self.update_ui(0)
        
    def set_loop_in_at_selection(self) -> None:
        self.session.set_loop_in_at_selection()

    def set_loop_out_at_selection(self) -> None:
        self.session.set_loop_out_at_selection()

    def on_toggle_loop(self) -> None:
        enabled = self.widgets.loop_var.get()
        self.session.set_loop_enabled(enabled)


    def _stick_to_next_bar_enabled(self) -> bool:
        # Safe guard in case widgets aren't fully initialized
        return bool(getattr(self.widgets, "stick_to_bar_var", None) and self.widgets.stick_to_bar_var.get())

    def _schedule_on_next_bar(self, callback: Callable[[], None]) -> None:
        """
        Call `callback` aligned so that it starts exactly on beat 1
        of the next bar, according to Session/metronome info.

        If 'stick to next bar' is disabled or alignment info is unavailable,
        call immediately.
        """
        # If stick-to-next-bar is off, just run now
        if not self._stick_to_next_bar_enabled():
            callback()
            return

        now_ms = int(time.time() * 1000)
        delay_ms = self.session.compute_next_bar_delay_ms(now_ms)

        if delay_ms is None:
            # No reliable alignment info → run immediately
            callback()
            return

        self.root.after(delay_ms, callback)

    # ====== Editing (selection + pitch) ========================

    def move_selection(self, delta: int) -> None:
        new_idx = self.session.move_selection(delta)
        if new_idx is not None:
            self.update_ui(new_idx)

    def change_selected_pitch(self, delta_steps: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return

        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=transpose_pitch_diatonic,
        )

        if new_idx is None:
            return

        # 1) Sync UI score
        self.widgets.set_score(self.score)

        # 2) Sync playback's view of notes for UI highlighting
        self.player.notes_flat = self.editor.get_flat_notes()

        # 3) Sync active MidiClip events so AUDIO matches edited score
        self.session.sync_active_midi_clip_from_score()

        # 5) Update UI selection
        self.update_ui(new_idx)

    def on_key(self, event) -> None:
        key = event.keysym

        if key in ("a", "A"):
            self.move_selection(-1)
        elif key in ("d", "D"):
            self.move_selection(1)
        elif key == "Up":
            self.change_selected_pitch(+1)
        elif key == "Down":
            self.change_selected_pitch(-1)
        elif key in ("i", "I"):
            self.set_loop_in_at_selection()
        elif key in ("o", "O"):
            self.set_loop_out_at_selection()
        elif key in ("m", "M"):
            # Turn current note into an interval selection
            self.select_interval_for_current_note()
        elif key in ("n", "N"):
            # Back to note-selection mode
            self.clear_interval_selection()

    # ====== Main loop ==========================================

    def run(self) -> None:
        self.root.mainloop()
# ui/staff_view.py
from __future__ import annotations

import tkinter as tk
from typing import List, Tuple, Optional, Dict

from domain.score import Score
from domain.theory import pitch_to_diatonic_index
from domain.notation import (
    NotatedScore,
    NotatedAtom,
    notated_duration_to_beats,
    build_notated_score,
)

from notation.style_config import StyleConfig
from notation.formatting import (
    duration_kind_from_beats,
    is_filled_notehead,
    is_beamable,
    beams_for_kind,
)
from notation.drawing import (
    NoteDrawingContext,
    draw_notehead,
    draw_stem,
    draw_beam_group,
    StemDirection,
    draw_treble_clef,
    draw_time_signature,
)

try:
    from PIL import Image, ImageTk  # type: ignore
except ImportError:  # graceful fallback
    Image = None
    ImageTk = None


class StaffView(tk.Canvas):
    """
    Simple staff renderer:

    - 5 horizontal lines.
    - Notes drawn with basic sheet-music-like features:
      stems, filled/hollow heads, simple beams.
    - highlight_note(index) highlights a single note by flat index
      (same order as score.all_notes()).
    - set_selection_region(measure_index, beat_start, beat_end) draws
      a translucent rectangle over the selected beat range in that measure.
    """

    def __init__(self, master, width: int = 800, height: int = 160, **kwargs):
        super().__init__(master, width=width, height=height, bg="white", **kwargs)

        # External source of truth
        self.score: Optional[Score] = None

        # INTERNAL: derived from score for layout and notation
        self._notated_score: Optional[NotatedScore] = None

        # Flattened note visuals: parallel arrays, one entry per visual note
        self.note_positions: List[Tuple[float, float]] = []
        self.note_atoms: List[Optional[NotatedAtom]] = []

        # Additional per-note metadata to support stems and beams
        self._note_measure_index: List[int] = []
        self._note_duration_beats: List[float] = []
        self._note_step: List[int] = []  # diatonic steps relative to B4

        # Interaction state
        self.highlight_index: int = -1
        self.selection_region: Optional[Tuple[int, float, float]] = None

        # Layout margins
        self.left_margin = 40
        self.right_margin = 20
        self.top_margin = 20
        self.bottom_margin = 20

        # Pitch/staff mapping
        self._letter_order = ["C", "D", "E", "F", "G", "A", "B"]
        self._ref_pitch = "B4"  # middle staff line

        # Staff geometry cache (computed on each redraw)
        self._line_spacing: float = 0.0
        self._middle_line_y: float = 0.0

        # Visual style (can be swapped later)
        self.style = StyleConfig()
        # Horizontal layout & scrolling
        self.px_per_beat: float = 60.0   # tune later
        self._content_width: int = width  # total logical width of the score
        self.info_width = self.style.info_region_width
        self.measure_width = 90.0
        # Treble clef image cache (optional, uses assets/treble_clef.png)
        self._clef_image = None
        self._clef_photo = None

    # ===== External API ========================================

    def set_score(self, score: Score) -> None:
        """
        External entry point: Score is the only source of truth.
        StaffView builds its own NotatedScore internally.
        """
        self.score = score
        self._notated_score = build_notated_score(score)
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def set_notated_score(self, nscore: NotatedScore) -> None:
        """
        Main entry point for sheet layout: uses NotatedScore to derive
        positions and (later) stems, beams, etc.
        """
        self._notated_score = nscore
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def highlight_note(self, index: int) -> None:
        """
        Highlight the note at flat index `index` (same order as Score.all_notes()).
        If index is out of range, clears the highlight.
        """
        if (
            self.score is None
            and self._notated_score is None
        ) or not self.note_positions:
            self.highlight_index = -1
        elif index < 0 or index >= len(self.note_positions):
            self.highlight_index = -1
        else:
            self.highlight_index = index
        self._redraw()

    def set_selection_region(
        self,
        measure_index: int,
        beat_start: float,
        beat_end: float,
    ) -> None:
        """
        Called by Widgets / App to visualize the selected time interval
        within a given measure.
        """
        self.selection_region = (measure_index, beat_start, beat_end)
        self._redraw()

    # ===== Internal helpers ====================================
    
    def scroll_to_note(self, index: int, margin: float = 80.0) -> None:
        """
        Ensure the note at `index` is visible within the horizontal viewport.
        Keeps a margin from the edges when possible.
        """
        if index < 0 or index >= len(self.note_positions):
            return

        content_width = max(self._content_width, 1)
        visible_width = int(self["width"])

        if visible_width >= content_width:
            # Everything fits; nothing to scroll
            return

        x, _ = self.note_positions[index]
        
        first_frac, last_frac = self.xview()
        first_x = first_frac * content_width
        last_x = last_frac * content_width

        # If within [first+margin, last-margin], keep as is
        if first_x + margin <= x <= last_x - margin:
            return

        # Otherwise, try to center the note
        new_first_x = x - visible_width / 2.0
        new_first_x = max(0.0, min(new_first_x, content_width - visible_width))
        new_first_frac = new_first_x / content_width
        self.xview_moveto(new_first_frac)


    def _compute_staff_geometry(self) -> Tuple[int, int, float, float, float]:
        """
        Compute and cache staff geometry for the *visible* area:
        width, height, line spacing, top line, bottom line, and middle line y.
        """
        width = int(self["width"])   # visible width (clip)
        height = int(self["height"])

        staff_height = height - self.top_margin - self.bottom_margin
        line_spacing = staff_height / 4.0  # 4 gaps between 5 lines
        top_line_y = self.top_margin
        bottom_line_y = top_line_y + 4 * line_spacing

        self._line_spacing = line_spacing
        self._middle_line_y = top_line_y + 2 * line_spacing  # 3rd (middle) line

        return width, height, top_line_y, bottom_line_y, line_spacing


    def _pitch_to_staff_step(self, pitch: str) -> int:
        """
        Convert pitch to a diatonic step relative to B4 = 0.
        Each step is one line/space on the staff.
        """
        idx = pitch_to_diatonic_index(pitch)
        ref_idx = pitch_to_diatonic_index(self._ref_pitch)
        return idx - ref_idx

    def get_beats_per_bar(self):
        beats_per_bar = (
                self.score.time_signature[0]
                if self.score and self.score.time_signature
                else 4
            )
        if beats_per_bar <= 0:
                beats_per_bar = 4
        return beats_per_bar
    
    def _recompute_note_positions(self) -> None:
        """
        Build:
            self.note_positions: (x, y) for each visual atom
            self.note_atoms:     corresponding NotatedAtom (or None)
            self._note_measure_index
            self._note_duration_beats
            self._note_step
        Preferred: use internal _notated_score.
        Fallback: derive from raw Score if needed.
        """
        self.note_positions = []
        self.note_atoms = []
        self._note_measure_index = []
        self._note_duration_beats = []
        self._note_step = []
        
        width, height, top_line_y, _, line_spacing = self._compute_staff_geometry()
        half_step = line_spacing / 2.0
        middle_line_y = self._middle_line_y

        # Reset content width for recompute; we'll update it below
        self._content_width = width  # fallback

               # --- Preferred path: NotatedScore ---
        if self._notated_score is not None:
            nscore = self._notated_score
            measures = nscore.measures
            if not measures:
                return

            beats_per_bar = self.get_beats_per_bar()

            measure_width = beats_per_bar * self.px_per_beat
            self.measure_width = measure_width

            content_x = self.left_margin + self.info_width
            for m in measures:
                measure_index = m.index
                measure_start_x = content_x

                for atom in m.atoms:
                    beat_start = atom.beat_start.to_float()
                    dur_beats = notated_duration_to_beats(
                        atom.duration, m.time_signature
                    )
                    center_beat = beat_start + dur_beats / 2.0

                    # 0..beats_per_bar → 0..1 within measure
                    t = min(max(center_beat / float(beats_per_bar), 0.0), 1.0)
                    x = measure_start_x  + t * measure_width

                    step = self._pitch_to_staff_step(atom.pitch)
                    y = middle_line_y - step * half_step

                    self.note_positions.append((x, y))
                    self.note_atoms.append(atom)
                    self._note_measure_index.append(measure_index)
                    self._note_duration_beats.append(dur_beats)
                    self._note_step.append(step)

                content_x += measure_width

            self._content_width = int(content_x + self.right_margin)
            # scrolling region is in canvas coords: [0, 0, content_width, height]
            self.config(scrollregion=(0, 0, self._content_width, height))
            return  # done

        # --- Fallback: old Score-based layout ---
        # --- Fallback: old Score-based layout ---
        if self.score is None:
            return

        measures = self.score.measures
        if not measures:
            return

        beats_per_bar = self.get_beats_per_bar()
        
        measure_width = beats_per_bar * self.px_per_beat
        self.measure_width = measure_width
        content_x = self.left_margin
        for mi, measure in enumerate(measures):
            measure_start_x = content_x

            beat_pos = 0.0
            for note in measure.notes:
                center_beat = beat_pos + note.duration_beats / 2.0
                t = min(max(center_beat / beats_per_bar, 0.0), 1.0)
                x = measure_start_x + t * measure_width

                step = self._pitch_to_staff_step(note.pitch)
                y = middle_line_y - step * half_step

                self.note_positions.append((x, y))
                self.note_atoms.append(None)
                self._note_measure_index.append(mi)
                self._note_duration_beats.append(note.duration_beats)
                self._note_step.append(step)

                beat_pos += note.duration_beats

            content_x += measure_width

        self._content_width = int(content_x + self.right_margin)
        self.config(scrollregion=(0, 0, self._content_width, height))

    def _redraw(self) -> None:
        self.delete("all")
        self._draw_selection_overlay()
        self._recompute_note_positions()
        self._draw_staff()
        self._draw_notes()
        
        
    def _draw_staff(self) -> None:
        """Draw the 5 staff lines + barlines + beat grid + clef + time signature."""
        _, _, top_line_y, bottom_line_y, line_spacing = self._compute_staff_geometry()
        cfg = self.style
        info_w = self.info_width
        num_measures = len(self.score.measures)

        # --- horizontal staff lines ---
        for i in range(5):
            y = top_line_y + i * line_spacing
            self.create_line(
                self.left_margin,
                y,
                self.left_margin + self.info_width + self.measure_width * num_measures,
                y,
                fill=cfg.staff_line_color,
                width=cfg.staff_line_width,
            )

        # --- clef + time sig in the info area ---
        self._draw_clef_and_time_signature(top_line_y, line_spacing)

        # --- barlines + beat grid (if we have a score) ---
        if self.score is None or not self.score.measures:
            return

        if num_measures <= 0:
            num_measures = 4

        beats_per_bar = self.get_beats_per_bar()
        # Draw barlines (between measures and at the end)
        for mi in range(num_measures + 1):
            x_bar = self.left_margin + info_w + mi * self.measure_width
            self.create_line(
                x_bar,
                top_line_y,
                x_bar,
                bottom_line_y,
                fill=cfg.barline_color,
                width=cfg.barline_width,
            )

        # Draw light beat grid inside each measure
        if beats_per_bar > 0:
            for mi in range(num_measures):
                measure_start_x = self.left_margin + info_w + mi * self.measure_width
                for b in range(1, beats_per_bar):
                    t = b / beats_per_bar
                    x = measure_start_x + t * self.measure_width
                    self.create_line(
                        x,
                        top_line_y,
                        x,
                        bottom_line_y,
                        fill=cfg.beat_grid_color,
                        width=cfg.beat_grid_width,
                        dash=(2, 4),
                    )

    def _draw_selection_overlay(self) -> None:
        if self.score is None or self.selection_region is None:
            return
        measures = self.score.measures
        if not measures:
            return

        measure_index, beat_start, beat_end = self.selection_region
        if measure_index < 0 or measure_index >= len(measures):
            return

        height = int(self["height"])
        beats_per_bar = self.get_beats_per_bar()

        measure_start_x = self.left_margin + self.info_width + measure_index * self.measure_width

        bs = max(0.0, beat_start)
        be = max(bs, beat_end)
        max_be = float(beats_per_bar)
        if bs > max_be:
            return
        be = min(be, max_be)

        t0 = bs / beats_per_bar
        t1 = be / beats_per_bar
        x0 = measure_start_x + t0 * self.measure_width
        x1 = measure_start_x + t1 * self.measure_width

        y0 = self.top_margin - 5
        y1 = height - self.bottom_margin + 5

        self.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=self.style.selection_fill,
            outline="",
        )

    # ===== Graphical helpers for note appearance =================

    def _draw_notes(self) -> None:
        """
        Draw noteheads, stems and beams using the flattened arrays computed in
        _recompute_note_positions().
        """
        if not self.note_positions:
            return

        # Make sure geometry cache is up-to-date
        self._compute_staff_geometry()

        ctx = NoteDrawingContext(
            canvas=self,
            style=self.style,
            line_spacing=self._line_spacing,
            middle_line_y=self._middle_line_y,
        )

        n = len(self.note_positions)

        # First pass: gather per-note drawing info.
        note_info = []
        for idx in range(n):
            x, y = self.note_positions[idx]
            beats = (
                self._note_duration_beats[idx]
                if idx < len(self._note_duration_beats)
                else 1.0
            )
            kind = duration_kind_from_beats(beats)
            filled = is_filled_notehead(kind)
            beams = beams_for_kind(kind)
            measure_index = (
                self._note_measure_index[idx]
                if idx < len(self._note_measure_index)
                else 0
            )
            step = self._note_step[idx] if idx < len(self._note_step) else 0

            # Stem direction: notes on or below middle line -> stem up,
            # notes above middle line -> stem down.
            # step > 0 means above B4 (our reference at middle line).
            stem_dir: StemDirection = "down" if step > 0 else "up"

            note_info.append(
                {
                    "idx": idx,
                    "x": x,
                    "y": y,
                    "kind": kind,
                    "filled": filled,
                    "beams": beams,
                    "beamable": is_beamable(kind),
                    "measure_index": measure_index,
                    "stem_dir": stem_dir,
                    "highlight": (idx == self.highlight_index),
                }
            )

        # Second pass: draw noteheads and stems, record stem tip positions
        # for potential beams.
        stem_tips: Dict[int, Tuple[float, float]] = {}

        for info in note_info:
            idx = info["idx"]
            x = info["x"]
            y = info["y"]
            filled = info["filled"]
            stem_dir = info["stem_dir"]
            kind = info["kind"]
            highlight = info["highlight"]

            # Notehead
            draw_notehead(
                ctx,
                x,
                y,
                filled=filled,
                highlighted=highlight,
            )

            # Stems: whole notes don't have stems; others do.
            if kind != "whole":
                tip_x, tip_y = draw_stem(ctx, x, y, stem_dir)
                stem_tips[idx] = (tip_x, tip_y)

        # Third pass: build simple beam groups and draw beams.
        current_group: List[Dict] = []

        def flush_group() -> None:
            if len(current_group) < 2:
                return
            # Smallest beam count wins (so mix of 8th/16th gets at least one beam).
            group_beams = min(info["beams"] for info in current_group)
            if group_beams <= 0:
                return

            # All group notes have the same stem direction by construction.
            direction: StemDirection = current_group[0]["stem_dir"]

            # Collect stem tips in visual order.
            tips: List[Tuple[float, float]] = []
            for info in current_group:
                tip = stem_tips.get(info["idx"])
                if tip is not None:
                    tips.append(tip)

            if len(tips) >= 2:
                draw_beam_group(ctx, tips, direction, group_beams)

        last_measure = None
        last_stem_dir: Optional[StemDirection] = None

        for info in note_info:
            if info["beamable"]:
                same_measure = (
                    last_measure is None
                    or info["measure_index"] == last_measure
                )
                same_direction = (
                    last_stem_dir is None
                    or info["stem_dir"] == last_stem_dir
                )

                if current_group and (not same_measure or not same_direction):
                    # Beam group broken by measure or stem direction change.
                    flush_group()
                    current_group = []

                current_group.append(info)
                last_measure = info["measure_index"]
                last_stem_dir = info["stem_dir"]
            else:
                # Non-beamable note breaks any ongoing group.
                if current_group:
                    flush_group()
                    current_group = []
                    last_measure = None
                    last_stem_dir = None

        # Flush trailing group
        if current_group:
            flush_group()

    def _draw_treble_clef_image(
        self,
        top_line_y: float,
        line_spacing: float,
    ) -> bool:
        """
        Try to draw the treble clef from assets/treble_clef.png.
        Returns True on success, False if we should fall back to vector/glyph.
        """
        if Image is None or ImageTk is None:
            return False

        # Lazy-load original image
        if self._clef_image is None:
            try:
                self._clef_image = Image.open("assets/treble_clef.png")
            except Exception:
                return False

        # Scale image to staff height
        staff_height = 4 * line_spacing
        target_h = int(staff_height * 1.2)
        if target_h <= 0:
            target_h = 10

        w, h = self._clef_image.size
        scale = target_h / float(h)
        target_w = max(1, int(w * scale))

        img_resized = self._clef_image.resize((target_w, target_h), Image.LANCZOS)
        self._clef_photo = ImageTk.PhotoImage(img_resized)

        x = self.left_margin + self.info_width * 0.3
        y = top_line_y + 2 * line_spacing  # around middle of staff

        self.create_image(x, y, image=self._clef_photo)
        return True

    def _draw_clef_and_time_signature(
        self,
        top_line_y: float,
        line_spacing: float,
    ) -> None:
        """
        Draw treble clef + time signature inside the info region, before the first barline.
        """
        ctx = NoteDrawingContext(
            canvas=self,
            style=self.style,
            line_spacing=line_spacing,
            middle_line_y=self._middle_line_y,
        )

        info_w = self.info_width

        # 1) Clef: try image, fall back to glyph
        drew_image = self._draw_treble_clef_image(top_line_y, line_spacing)
        if not drew_image:
            clef_x = self.left_margin + info_w * 0.3
            draw_treble_clef(ctx, clef_x, top_line_y, line_spacing)

        # 2) Time signature (if available)
        if self.score is not None and self.score.time_signature:
            num, den = self.score.time_signature
            ts_x = self.left_margin + info_w * 0.75
            draw_time_signature(ctx, ts_x, top_line_y, line_spacing, num, den)
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from ui.staff_view import StaffView
from domain.score import Score

if TYPE_CHECKING:
    from app import App
    from domain.notation import NotatedScore


class Widgets:
    """
    Builds all Tk widgets and binds their commands directly to App methods.
    Exposes a small API for App to update the view.
    """

    def __init__(self, root: tk.Tk, app: "App") -> None:
        self.root = root
        self.app = app

        # === Menu: File ===
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open...", command=self.app.on_open)
        filemenu.add_command(label="Save As...", command=self.app.on_save_as)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.app.on_quit)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        # === Staff view + note label ===
        # === Staff view + horizontal scroll ===
        staff_frame = tk.Frame(root)
        staff_frame.pack(pady=5, fill="x", expand=False)

        self.staff_hbar = tk.Scrollbar(staff_frame, orient=tk.HORIZONTAL)
        self.staff_hbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.staff_view = StaffView(staff_frame, width=800, height=160)
        self.staff_view.pack(side=tk.TOP, fill="x", expand=False)

        self.staff_view.config(xscrollcommand=self.staff_hbar.set)
        self.staff_hbar.config(command=self.staff_view.xview)

        self.staff_view.set_score(app.score)

        self.note_label = tk.Label(root, font=("Arial", 24))
        self.note_label.pack(pady=10)

        # === Metronome panel ===
        metro_frame = tk.Frame(root)
        metro_frame.pack(pady=5)

        tk.Label(metro_frame, text="Metronome:").pack(side=tk.LEFT)

        self.metro_canvas = tk.Canvas(
            metro_frame,
            width=24,
            height=24,
            highlightthickness=0,
        )
        self.metro_canvas.pack(side=tk.LEFT, padx=5)
        self._beat_circle = self.metro_canvas.create_oval(
            4, 4, 20, 20, fill="grey", outline="black"
        )

        self.metro_on_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            metro_frame,
            text="On",
            variable=self.metro_on_var,
            command=self.app.on_toggle_metronome,
        ).pack(side=tk.LEFT)

        # === Tempo control ===
        tempo_frame = tk.Frame(root)
        tempo_frame.pack(pady=5)
        tk.Label(tempo_frame, text="Tempo (bpm):").pack(side=tk.LEFT)

        self.tempo_var = tk.StringVar(value=str(app.score.tempo_bpm))

        def _tempo_changed(*_):
            self.app.on_tempo_change(self.tempo_var.get())

        tempo_entry = tk.Entry(tempo_frame, textvariable=self.tempo_var, width=5)
        tempo_entry.pack(side=tk.LEFT)
        self.tempo_var.trace_add("write", _tempo_changed)

        # === Transport ===
        controls = tk.Frame(root)
        controls.pack(pady=10)

        tk.Button(controls, text="Start", command=self.app.on_start).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(
            controls,
            text="Play from selected",
            command=self.app.on_play_from_selected,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(controls, text="Pause", command=self.app.on_pause).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(controls, text="Stop", command=self.app.on_stop).pack(
            side=tk.LEFT, padx=5
        )

        # Stick-to-next-bar option:
        # App reads this via _stick_to_next_bar_enabled(); no callback needed here.
        self.stick_to_bar_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            controls,
            text="Stick to next bar",
            variable=self.stick_to_bar_var,
        ).pack(side=tk.LEFT, padx=10)

        # Loop toggle
        self.loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            controls,
            text="Loop",
            variable=self.loop_var,
            command=self.app.on_toggle_loop,
        ).pack(side=tk.LEFT, padx=10)

        # === Status bar ===
        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(root, textvariable=self.status_var, anchor="w")
        status_label.pack(fill="x", side=tk.BOTTOM, padx=5, pady=3)

    # --------- Small API for App to control the view -----------

    def metro_visual(self, strong: bool) -> None:
        color = "tomato" if strong else "gold"
        self.metro_canvas.itemconfig(self._beat_circle, fill=color)
        self.root.after(
            80, lambda: self.metro_canvas.itemconfig(self._beat_circle, fill="grey")
        )

    def set_score(self, score: Score) -> None:
        self.staff_view.set_score(score)

    def set_note_list(self, text: str) -> None:
        self.note_label.config(text=text)

    def highlight_note(self, index: int) -> None:
        # StaffView already handles out-of-range gracefully (we used -1 in App)
        self.staff_view.highlight_note(index)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_selection_region(
        self,
        measure_index: int,
        beat_start: float,
        beat_end: float,
    ) -> None:
        """
        Hook for a visual overlay on the staff.
        Only calls through if StaffView implements set_selection_region.
        """
        if hasattr(self.staff_view, "set_selection_region"):
            self.staff_view.set_selection_region(measure_index, beat_start, beat_end)
            
    def scroll_to_note_index(self, index: int) -> None:
        """
        Let App request horizontal scrolling so that a given note index
        stays in view.
        """
        if hasattr(self.staff_view, "scroll_to_note"):
            self.staff_view.scroll_to_note(index)