# engine/project.py
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


@dataclass
class MidiEvent:
    """
    Minimal MIDI-like event for our engine.

    For now:
    - start_beats: absolute position in beats from project start
    - duration_beats: length in beats
    - pitch: symbolic (e.g. "C5"); later we can add midi_note: int
    - velocity: fixed-ish for now
    """
    start_beats: float
    duration_beats: float
    pitch: str
    velocity: int = 100


@dataclass
class Clip:
    """
    Base clip on the timeline.
    """
    start_beats: float
    length_beats: float


@dataclass
class MidiClip(Clip):
    """
    A clip containing MIDI-style events (our flattened Score).
    """
    events: List[MidiEvent] = field(default_factory=list)


class TrackType(str, Enum):
    MIDI = "midi"
    AUDIO = "audio"


@dataclass
class Track:
    name: str
    track_type: TrackType
    clips: List[Clip] = field(default_factory=list)


@dataclass
class Project:
    tempo_bpm: int
    time_signature: tuple[int, int]
    tracks: List[Track] = field(default_factory=list)
