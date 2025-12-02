# domain/theory.py

from __future__ import annotations

from typing import Final

LETTER_ORDER: Final[list[str]] = ["C", "D", "E", "F", "G", "A", "B"]
MIN_DIATONIC_INDEX: Final[int] = LETTER_ORDER.index("E") + 7 * 2  # E4
MAX_DIATONIC_INDEX: Final[int] = LETTER_ORDER.index("F") + 7 * 7  # F5


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
