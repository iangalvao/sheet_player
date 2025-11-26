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
