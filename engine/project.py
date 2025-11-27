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

