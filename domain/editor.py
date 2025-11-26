# editor.py
from __future__ import annotations

from typing import Callable, List, Tuple, Optional
from engine.timebase import BeatTime
from domain.score import Score


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
        self._notes_flat: List[Tuple[int, int, object]] = []
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

    def get_flat_notes(self) -> List[Tuple[int, int, object]]:
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
