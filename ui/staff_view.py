from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, List, Tuple, Optional

from domain.score import Score
from domain.theory import pitch_to_diatonic_index


if TYPE_CHECKING:
    from domain.notation import NotatedScore
class StaffView(tk.Canvas):
    """
    Simple staff renderer:

    - 5 horizontal lines.
    - Notes drawn as circles based on pitch and (local) time in the measure.
    - highlight_note(index) highlights a single note by flat index
      (same order as score.all_notes()).
    - set_selection_region(measure_index, beat_start, beat_end) draws
      a translucent rectangle over the selected beat range in that measure.
    """

    def __init__(self, master, width: int = 800, height: int = 160, **kwargs):
        super().__init__(master, width=width, height=height, bg="white", **kwargs)
        self.score: Optional[Score] = None

        # Flattened note positions: one per note in score.all_notes() order
        self.note_positions: List[Tuple[float, float]] = []

        # Index of currently highlighted note in note_positions (or -1 for none)
        self.highlight_index: int = -1

        # Selection region for overlay: (measure_index, beat_start, beat_end)
        self.selection_region: Optional[Tuple[int, float, float]] = None

        # Layout parameters
        self.left_margin = 40
        self.right_margin = 20
        self.top_margin = 20
        self.bottom_margin = 20

        # Pitch mapping reference
        self._letter_order = ["C", "D", "E", "F", "G", "A", "B"]
        # We'll treat B4 as the middle staff line (step = 0)
        self._ref_pitch = "B4"

    # ===== External API ========================================

    def set_score(self, score: Score) -> None:
        self.score = score
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def highlight_note(self, index: int) -> None:
        """
        Highlight the note at flat index `index` (same order as Score.all_notes()).
        If index is out of range, clears the highlight.
        """
        if self.score is None or not self.note_positions:
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

    def _pitch_to_staff_step(self, pitch: str) -> int:
        """
        Convert pitch to a diatonic step relative to B4 = 0.
        Each step is one line/space on the staff.
        """
        idx = pitch_to_diatonic_index(pitch)
        ref_idx = pitch_to_diatonic_index(self._ref_pitch)
        return idx - ref_idx

    def _recompute_note_positions(self) -> None:
        """
        Build self.note_positions: (x, y) for each note in score.all_notes().
        Horizontal position is proportional to beat position within its measure.
        Vertical position is based on pitch relative to B4.
        """
        self.note_positions = []
        if self.score is None:
            return

        measures = self.score.measures
        if not measures:
            return

        width = int(self["width"])
        height = int(self["height"])

        usable_width = width - self.left_margin - self.right_margin
        num_measures = len(measures)
        if num_measures <= 0:
            return

        measure_width = usable_width / num_measures

        # Vertical layout: 5 lines, centered
        staff_height = height - self.top_margin - self.bottom_margin

        # IMPORTANT: must match _draw_staff()
        line_spacing = staff_height / 4.0          # distance between staff lines
        half_step = line_spacing / 2.0             # one diatonic step (line or space)

        # Middle line (line 3) is 2 * line_spacing below top line
        middle_line_y = self.top_margin + 2 * line_spacing

        # Time mapping: use beats within each measure
        beats_per_bar = self.score.time_signature[0] if self.score.time_signature else 4

        for mi, measure in enumerate(measures):
            measure_start_x = self.left_margin + mi * measure_width

            beat_pos = 0.0
            for ni, note in enumerate(measure.notes):
                # Horizontal: center by beat
                center_beat = beat_pos + note.duration_beats / 2.0
                if beats_per_bar > 0:
                    t = min(max(center_beat / beats_per_bar, 0.0), 1.0)
                else:
                    t = 0.0
                x = measure_start_x + t * measure_width

                # Vertical: pitch -> staff steps (each step is a line or space)
                step = self._pitch_to_staff_step(note.pitch)
                y = middle_line_y - step * half_step

                self.note_positions.append((x, y))
                beat_pos += note.duration_beats

    def _redraw(self) -> None:
        self.delete("all")
        self._draw_staff()
        self._draw_selection_overlay()
        self._draw_notes()

    def _draw_staff(self) -> None:
        """Draw the 5 staff lines + barlines + beat grid."""
        width = int(self["width"])
        height = int(self["height"])

        staff_height = height - self.top_margin - self.bottom_margin
        # 4 spaces -> 5 lines => 4 gaps; so line_spacing * 4 = staff_height
        line_spacing = staff_height / 4.0
        top_line_y = self.top_margin
        bottom_line_y = top_line_y + 4 * line_spacing

        # --- horizontal staff lines ---
        for i in range(5):
            y = top_line_y + i * line_spacing
            self.create_line(
                self.left_margin,
                y,
                width - self.right_margin,
                y,
                fill="black",
                width=1.2,
            )

        # --- barlines + beat grid (if we have a score) ---
        if self.score is None or not self.score.measures:
            return

        measures = self.score.measures
        num_measures = len(measures)

        usable_width = width - self.left_margin - self.right_margin
        if num_measures <= 0:
            return
        measure_width = usable_width / num_measures

        beats_per_bar = self.score.time_signature[0] if self.score.time_signature else 4

        # Draw barlines (between measures and at the end)
        for mi in range(num_measures + 1):
            x_bar = self.left_margin + mi * measure_width
            self.create_line(
                x_bar,
                top_line_y,
                x_bar,
                bottom_line_y,
                fill="#444444",
                width=1.2,
            )

        # Draw light beat grid inside each measure
        if beats_per_bar > 0:
            for mi in range(num_measures):
                measure_start_x = self.left_margin + mi * measure_width
                for b in range(1, beats_per_bar):
                    t = b / beats_per_bar
                    x = measure_start_x + t * measure_width
                    self.create_line(
                        x,
                        top_line_y,
                        x,
                        bottom_line_y,
                        fill="#dddddd",
                        width=1.0,
                        dash=(2, 4),
                    )

    def _draw_selection_overlay(self) -> None:
        """
        Draw a light rectangle showing the selected beat range in a measure.
        """
        if self.score is None or self.selection_region is None:
            return

        measures = self.score.measures
        if not measures:
            return

        measure_index, beat_start, beat_end = self.selection_region
        if measure_index < 0 or measure_index >= len(measures):
            return

        width = int(self["width"])
        height = int(self["height"])
        usable_width = width - self.left_margin - self.right_margin
        num_measures = len(measures)
        if num_measures <= 0:
            return

        measure_width = usable_width / num_measures
        measure_start_x = self.left_margin + measure_index * measure_width

        beats_per_bar = self.score.time_signature[0] if self.score.time_signature else 4
        if beats_per_bar <= 0:
            return

        # Clamp beat range
        bs = max(0.0, beat_start)
        be = max(bs, beat_end)
        max_be = float(beats_per_bar)
        if bs > max_be:
            return
        be = min(be, max_be)

        t0 = bs / beats_per_bar
        t1 = be / beats_per_bar
        x0 = measure_start_x + t0 * measure_width
        x1 = measure_start_x + t1 * measure_width

        # Vertical bounds slightly above and below staff
        y0 = self.top_margin - 5
        y1 = height - self.bottom_margin + 5

        # Tkinter doesn't support alpha, but a light color works as an overlay.
        self.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill="#ffd8d8",  # light pink
            outline="",
        )
        
        
    def _draw_note(
        self,
        x: float,
        y: float,
        *,
        middle_line_y: float,
        line_spacing: float,
        highlight: bool = False,
        note_index: int | None = None,
    ) -> None:
        """
        Draw a single note head + stem at (x, y).

        Parameters
        ----------
        x, y:
            Center position of the note head (in canvas coordinates).
        middle_line_y:
            Y coordinate of the middle staff line (B4 reference).
        line_spacing:
            Vertical distance between adjacent staff lines.
        highlight:
            If True, draw the note head in "selected" style.
        note_index:
            Optional index in the flattened note list (for future use:
            duration, pitch-dependent styling, etc.).
        """
        note_radius_x = 6
        note_radius_y = 4

        # Decide stem direction:
        # - if the note is below the middle line (bigger y) → stem up
        # - if above the middle line → stem down
        stem_length = line_spacing * 3

        if y > middle_line_y:
            # stem up: start at right side of the head, go upwards
            stem_x = x + note_radius_x
            stem_y0 = y
            stem_y1 = y - stem_length
        else:
            # stem down: start at left side of the head, go downwards
            stem_x = x - note_radius_x
            stem_y0 = y
            stem_y1 = y + stem_length

        # Draw stem
        self.create_line(
            stem_x,
            stem_y0,
            stem_x,
            stem_y1,
            fill="black",
            width=1.2,
        )

        # Draw note head
        fill = "deepskyblue" if highlight else "white"
        outline = "black"

        self.create_oval(
            x - note_radius_x,
            y - note_radius_y,
            x + note_radius_x,
            y + note_radius_y,
            fill=fill,
            outline=outline,
            width=1.2,
        )

    def _draw_notes(self) -> None:
        if self.score is None or not self.note_positions:
            return

        width = int(self["width"])
        height = int(self["height"])

        staff_height = height - self.top_margin - self.bottom_margin
        line_spacing = staff_height / 4.0       # same as in _draw_staff
        top_line_y = self.top_margin
        middle_line_y = top_line_y + 2 * line_spacing

        for idx, (x, y) in enumerate(self.note_positions):
            highlight = (idx == self.highlight_index)

            self._draw_note(
                x=x,
                y=y,
                middle_line_y=middle_line_y,
                line_spacing=line_spacing,
                highlight=highlight,
                note_index=idx,
            )

    def set_notated_score(self, nscore: "NotatedScore") -> None:
        """
        Placeholder: accept a NotatedScore but ignore it for now.

        Later we'll migrate _recompute_note_positions to use this
        instead of raw Score.
        """
        # For now we just keep the existing behavior (derive from self.score).
        # When we switch, we might store `self.notated_score = nscore`
        # and recompute positions from it.
        pass