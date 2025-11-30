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
