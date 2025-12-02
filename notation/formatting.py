# notation/formatting.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DurationKind = Literal["whole", "half", "quarter", "eighth", "sixteenth"]


class DurationFormatter:
    """
    Encapsulates duration → drawing classification.
    """

    def classify(self, beats: float) -> DurationKind:
        """
        Clean 4/4 powers of two:

          4.0   -> "whole"
          2.0   -> "half"
          1.0   -> "quarter"
          0.5   -> "eighth"
          0.25  -> "sixteenth"

        Fallback: "quarter".
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

    def is_filled(self, kind: DurationKind) -> bool:
        """Whole/half are hollow; others filled."""
        return kind not in ("whole", "half")

    def beam_count(self, kind: DurationKind) -> int:
        """Number of beams for this duration."""
        if kind == "eighth":
            return 1
        if kind == "sixteenth":
            return 2
        return 0

    def is_beamable(self, kind: DurationKind) -> bool:
        return self.beam_count(kind) > 0


# Default singleton for convenience / backwards helpers
_default_duration_formatter = DurationFormatter()


# --- Backwards-compatible helpers (optional, can be removed later) -----

def duration_kind_from_beats(beats: float) -> DurationKind:
    return _default_duration_formatter.classify(beats)


def is_filled_notehead(kind: DurationKind) -> bool:
    return _default_duration_formatter.is_filled(kind)


def beams_for_kind(kind: DurationKind) -> int:
    return _default_duration_formatter.beam_count(kind)


def is_beamable(kind: DurationKind) -> bool:
    return _default_duration_formatter.is_beamable(kind)


# ---- Layout-related classes -------------------------------------------

@dataclass
class StaffLayoutConfig:
    """
    Geometric layout configuration for the staff.
    """
    left_margin: float = 40.0
    right_margin: float = 20.0
    top_margin: float = 20.0
    bottom_margin: float = 20.0

    # Space reserved for clef + key + time signature
    info_region_width: float = 90.0

    # Horizontal density: pixels per beat
    px_per_beat: float = 60.0


class HorizontalLayout:
    """
    Computes measure widths and note x-positions from beats and layout cfg.
    """

    def measure_width(self, beats_per_bar: float, cfg: StaffLayoutConfig) -> float:
        if beats_per_bar <= 0:
            beats_per_bar = 4.0
        return beats_per_bar * cfg.px_per_beat

    def note_center_x(
        self,
        measure_index: int,
        beat_start: float,
        duration_beats: float,
        beats_per_bar: float,
        cfg: StaffLayoutConfig,
    ) -> float:
        """
        Center of the note within the given measure, mapped to absolute x.
        """
        beats_per_bar = max(beats_per_bar, 1e-6)
        center_beat = beat_start + duration_beats / 2.0
        t = min(max(center_beat / beats_per_bar, 0.0), 1.0)

        measure_w = self.measure_width(beats_per_bar, cfg)
        measure_start_x = cfg.left_margin + cfg.info_region_width + measure_index * measure_w
        return measure_start_x + t * measure_w


# ---- Pitch mapping -----------------------------------------------------

from domain.theory import pitch_to_diatonic_index  # type: ignore


class PitchMapper:
    """
    Maps pitches like 'C4' to diatonic steps relative to a reference pitch.
    """

    def __init__(self, ref_pitch: str = "B4") -> None:
        self.ref_pitch = ref_pitch
        self._ref_idx = pitch_to_diatonic_index(ref_pitch)

    def step_from_pitch(self, pitch: str) -> int:
        """
        Each step is one line/space on the staff.
        B4 = 0 by default (middle staff line).
        """
        idx = pitch_to_diatonic_index(pitch)
        return idx - self._ref_idx
