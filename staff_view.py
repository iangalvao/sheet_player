# staff_view.py
import tkinter as tk
from typing import List, Optional

from score import Score, Note  # adjust import if your Note is elsewhere

LETTER_ORDER = ["C", "D", "E", "F", "G", "A", "B"]


class StaffView(tk.Canvas):
    """
    Very simple treble-clef staff view:

    - 5 lines
    - notes mapped assuming treble clef:
        E4 = bottom line, F4 = space above, G4 = line, ...
        F5 = top line

    - Notes are drawn as ovals in time order (measure by measure).
    - highlight_note(index) colors the current note in red.
    """

    def __init__(self, master, width=800, height=160, **kwargs):
        super().__init__(master, width=width, height=height, bg="white", **kwargs)
        self.score: Optional[Score] = None

        self.margin_x = 40
        self.margin_y = 20
        self.line_spacing = 10  # vertical distance between staff lines

        # y of bottom staff line (E4)
        self.bottom_line_y = self.margin_y + 4 * self.line_spacing

        # Will store canvas item IDs for notes in flattened order
        self.note_items: List[int] = []

    # ---------- public API ----------

    def set_score(self, score: Score):
        """Set current score and redraw staff + notes."""
        self.score = score
        self.delete("all")
        self.note_items.clear()
        self._draw_staff()
        if self.score is not None:
            self._draw_notes()

    def highlight_note(self, index: int):
        """Highlight note by global index (in Score.all_notes order)."""
        # reset all to black
        for item in self.note_items:
            self.itemconfig(item, fill="black", outline="black")

        if 0 <= index < len(self.note_items):
            self.itemconfig(self.note_items[index], fill="red", outline="red")

    # ---------- drawing ----------

    def _draw_staff(self):
        width = int(self["width"])
        x0 = self.margin_x
        x1 = width - self.margin_x

        # 5 staff lines – bottom to top (E4..F5)
        for i in range(5):
            y = self.bottom_line_y - i * self.line_spacing
            self.create_line(x0, y, x1, y, width=1)

        # bar lines, if we have a score
        if self.score is not None:
            measures = len(self.score.measures)
            if measures > 0:
                total_width = x1 - x0
                measure_width = total_width / measures
                for i in range(measures + 1):
                    x = x0 + i * measure_width
                    self.create_line(
                        x,
                        self.bottom_line_y - 4 * self.line_spacing,
                        x,
                        self.bottom_line_y,
                        width=1,
                    )

    def _draw_notes(self):
        if self.score is None:
            return

        width = int(self["width"])
        x0 = self.margin_x
        x1 = width - self.margin_x

        measures = len(self.score.measures)
        if measures == 0:
            return

        total_width = x1 - x0
        measure_width = total_width / measures
        beats_per_bar = self.score.time_signature[0]

        # Flatten notes in the same order as Score.all_notes()
        for mi, measure in enumerate(self.score.measures):
            m_x0 = x0 + mi * measure_width
            pos_beats = 0.0  # beat position inside this measure

            for note in measure.notes:
                # Horizontal position: center of the note in its duration
                center_beat = pos_beats + note.duration_beats / 2.0
                x = m_x0 + (center_beat / beats_per_bar) * measure_width

                # Vertical position: based on pitch (treble clef)
                step = self._pitch_to_staff_step(note.pitch)
                if step is None:
                    # Rest: skip drawing for now (we'll handle rests in Step 6)
                    pos_beats += note.duration_beats
                    continue

                y = self._step_to_y(step)

                # Simple note head oval
                head_width = 10
                head_height = 8
                item = self.create_oval(
                    x - head_width / 2,
                    y - head_height / 2,
                    x + head_width / 2,
                    y + head_height / 2,
                    fill="black",
                    outline="black",
                )
                self.note_items.append(item)

                pos_beats += note.duration_beats

    # ---------- pitch → staff position helpers ----------

    def _pitch_to_staff_step(self, pitch: str) -> Optional[int]:
        """
        Map pitch like 'G4', 'C5', etc. to a staff step integer, where:

            step = 0  → E4 (bottom line)
            step = 1  → F4 (space)
            step = 2  → G4 (line)
            ...
            step = 8  → F5 (top line)

        Accidentals (#/b) are ignored for vertical position for now.
        Rests ('REST') return None.
        """
        up = pitch.upper()
        if up == "REST":
            return None

        # Split into (name, octave) like in your other code
        i = 0
        while i < len(pitch) and not pitch[i].isdigit():
            i += 1
        name = pitch[:i]
        octave_str = pitch[i:]
        if not octave_str:
            return None

        octave = int(octave_str)
        letter = name[0].upper()  # ignore accidental part for now

        if letter not in LETTER_ORDER:
            return None

        # Reference: E4 = step 0
        ref_letter = "E"
        ref_octave = 4

        idx_letter = LETTER_ORDER.index(letter)
        idx_ref = LETTER_ORDER.index(ref_letter)

        # diatonic steps from C, across octaves:
        total_steps = idx_letter + 7 * octave
        ref_steps = idx_ref + 7 * ref_octave

        step = total_steps - ref_steps
        return step

    def _step_to_y(self, step: int) -> float:
        """
        Convert staff step (0 = E4 bottom line, 1 = F4 space, etc.)
        to a y coordinate on the canvas.
        Each step is half a line spacing.
        """
        return self.bottom_line_y - step * (self.line_spacing / 2.0)
