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
