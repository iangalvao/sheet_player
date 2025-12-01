# ui/staff_view.py
from __future__ import annotations

import tkinter as tk
from typing import List, Tuple, Optional, Dict

from domain.score import Score
from domain.theory import pitch_to_diatonic_index
from domain.notation import (
    NotatedScore,
    NotatedAtom,
    notated_duration_to_beats,
    build_notated_score,
)

from notation.style_config import StyleConfig
from notation.formatting import (
    duration_kind_from_beats,
    is_filled_notehead,
    is_beamable,
    beams_for_kind,
)
from notation.drawing import (
    NoteDrawingContext,
    draw_notehead,
    draw_stem,
    draw_beam_group,
    StemDirection,
    draw_treble_clef,
    draw_time_signature,
)

try:
    from PIL import Image, ImageTk  # type: ignore
except ImportError:  # graceful fallback
    Image = None
    ImageTk = None


class StaffView(tk.Canvas):
    """
    Simple staff renderer:

    - 5 horizontal lines.
    - Notes drawn with basic sheet-music-like features:
      stems, filled/hollow heads, simple beams.
    - highlight_note(index) highlights a single note by flat index
      (same order as score.all_notes()).
    - set_selection_region(measure_index, beat_start, beat_end) draws
      a translucent rectangle over the selected beat range in that measure.
    """

    def __init__(self, master, width: int = 800, height: int = 160, **kwargs):
        super().__init__(master, width=width, height=height, bg="white", **kwargs)

        # External source of truth
        self.score: Optional[Score] = None

        # INTERNAL: derived from score for layout and notation
        self._notated_score: Optional[NotatedScore] = None

        # Flattened note visuals: parallel arrays, one entry per visual note
        self.note_positions: List[Tuple[float, float]] = []
        self.note_atoms: List[Optional[NotatedAtom]] = []

        # Additional per-note metadata to support stems and beams
        self._note_measure_index: List[int] = []
        self._note_duration_beats: List[float] = []
        self._note_step: List[int] = []  # diatonic steps relative to B4

        # Interaction state
        self.highlight_index: int = -1
        self.selection_region: Optional[Tuple[int, float, float]] = None

        # Layout margins
        self.left_margin = 40
        self.right_margin = 20
        self.top_margin = 20
        self.bottom_margin = 20

        # Pitch/staff mapping
        self._letter_order = ["C", "D", "E", "F", "G", "A", "B"]
        self._ref_pitch = "B4"  # middle staff line

        # Staff geometry cache (computed on each redraw)
        self._line_spacing: float = 0.0
        self._middle_line_y: float = 0.0

        # Visual style (can be swapped later)
        self.style = StyleConfig()
        # Horizontal layout & scrolling
        self.px_per_beat: float = 60.0   # tune later
        self._content_width: int = width  # total logical width of the score
        self.info_width = self.style.info_region_width
        self.measure_width = 90.0
        # Treble clef image cache (optional, uses assets/treble_clef.png)
        self._clef_image = None
        self._clef_photo = None

    # ===== External API ========================================

    def set_score(self, score: Score) -> None:
        """
        External entry point: Score is the only source of truth.
        StaffView builds its own NotatedScore internally.
        """
        self.score = score
        self._notated_score = build_notated_score(score)
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def set_notated_score(self, nscore: NotatedScore) -> None:
        """
        Main entry point for sheet layout: uses NotatedScore to derive
        positions and (later) stems, beams, etc.
        """
        self._notated_score = nscore
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def highlight_note(self, index: int) -> None:
        """
        Highlight the note at flat index `index` (same order as Score.all_notes()).
        If index is out of range, clears the highlight.
        """
        if (
            self.score is None
            and self._notated_score is None
        ) or not self.note_positions:
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
    
    def scroll_to_note(self, index: int, margin: float = 80.0) -> None:
        """
        Ensure the note at `index` is visible within the horizontal viewport.
        Keeps a margin from the edges when possible.
        """
        if index < 0 or index >= len(self.note_positions):
            return

        content_width = max(self._content_width, 1)
        visible_width = int(self["width"])

        if visible_width >= content_width:
            # Everything fits; nothing to scroll
            return

        x, _ = self.note_positions[index]
        
        first_frac, last_frac = self.xview()
        first_x = first_frac * content_width
        last_x = last_frac * content_width

        # If within [first+margin, last-margin], keep as is
        if first_x + margin <= x <= last_x - margin:
            return

        # Otherwise, try to center the note
        new_first_x = x - visible_width / 2.0
        new_first_x = max(0.0, min(new_first_x, content_width - visible_width))
        new_first_frac = new_first_x / content_width
        self.xview_moveto(new_first_frac)


    def _compute_staff_geometry(self) -> Tuple[int, int, float, float, float]:
        """
        Compute and cache staff geometry for the *visible* area:
        width, height, line spacing, top line, bottom line, and middle line y.
        """
        width = int(self["width"])   # visible width (clip)
        height = int(self["height"])

        staff_height = height - self.top_margin - self.bottom_margin
        line_spacing = staff_height / 4.0  # 4 gaps between 5 lines
        top_line_y = self.top_margin
        bottom_line_y = top_line_y + 4 * line_spacing

        self._line_spacing = line_spacing
        self._middle_line_y = top_line_y + 2 * line_spacing  # 3rd (middle) line

        return width, height, top_line_y, bottom_line_y, line_spacing


    def _pitch_to_staff_step(self, pitch: str) -> int:
        """
        Convert pitch to a diatonic step relative to B4 = 0.
        Each step is one line/space on the staff.
        """
        idx = pitch_to_diatonic_index(pitch)
        ref_idx = pitch_to_diatonic_index(self._ref_pitch)
        return idx - ref_idx

    def get_beats_per_bar(self):
        beats_per_bar = (
                self.score.time_signature[0]
                if self.score and self.score.time_signature
                else 4
            )
        if beats_per_bar <= 0:
                beats_per_bar = 4
        return beats_per_bar
    
    def _recompute_note_positions(self) -> None:
        """
        Build:
            self.note_positions: (x, y) for each visual atom
            self.note_atoms:     corresponding NotatedAtom (or None)
            self._note_measure_index
            self._note_duration_beats
            self._note_step
        Preferred: use internal _notated_score.
        Fallback: derive from raw Score if needed.
        """
        self.note_positions = []
        self.note_atoms = []
        self._note_measure_index = []
        self._note_duration_beats = []
        self._note_step = []
        
        width, height, top_line_y, _, line_spacing = self._compute_staff_geometry()
        half_step = line_spacing / 2.0
        middle_line_y = self._middle_line_y

        # Reset content width for recompute; we'll update it below
        self._content_width = width  # fallback

               # --- Preferred path: NotatedScore ---
        if self._notated_score is not None:
            nscore = self._notated_score
            measures = nscore.measures
            if not measures:
                return

            beats_per_bar = self.get_beats_per_bar()

            measure_width = beats_per_bar * self.px_per_beat
            self.measure_width = measure_width

            content_x = self.left_margin
            for m in measures:
                measure_index = m.index
                measure_start_x = content_x

                for atom in m.atoms:
                    beat_start = atom.beat_start.to_float()
                    dur_beats = notated_duration_to_beats(
                        atom.duration, m.time_signature
                    )
                    center_beat = beat_start + dur_beats / 2.0

                    # 0..beats_per_bar → 0..1 within measure
                    t = min(max(center_beat / float(beats_per_bar), 0.0), 1.0)
                    x = measure_start_x + self.info_width + t * measure_width

                    step = self._pitch_to_staff_step(atom.pitch)
                    y = middle_line_y - step * half_step

                    self.note_positions.append((x, y))
                    self.note_atoms.append(atom)
                    self._note_measure_index.append(measure_index)
                    self._note_duration_beats.append(dur_beats)
                    self._note_step.append(step)

                content_x += measure_width

            self._content_width = int(content_x + self.right_margin)
            # scrolling region is in canvas coords: [0, 0, content_width, height]
            self.config(scrollregion=(0, 0, self._content_width, height))
            return  # done

        # --- Fallback: old Score-based layout ---
        # --- Fallback: old Score-based layout ---
        if self.score is None:
            return

        measures = self.score.measures
        if not measures:
            return

        beats_per_bar = self.get_beats_per_bar()
        
        measure_width = beats_per_bar * self.px_per_beat
        self.measure_width = measure_width
        content_x = self.left_margin
        for mi, measure in enumerate(measures):
            measure_start_x = content_x

            beat_pos = 0.0
            for note in measure.notes:
                center_beat = beat_pos + note.duration_beats / 2.0
                t = min(max(center_beat / beats_per_bar, 0.0), 1.0)
                x = measure_start_x + t * measure_width

                step = self._pitch_to_staff_step(note.pitch)
                y = middle_line_y - step * half_step

                self.note_positions.append((x, y))
                self.note_atoms.append(None)
                self._note_measure_index.append(mi)
                self._note_duration_beats.append(note.duration_beats)
                self._note_step.append(step)

                beat_pos += note.duration_beats

            content_x += measure_width

        self._content_width = int(content_x + self.right_margin)
        self.config(scrollregion=(0, 0, self._content_width, height))

    def _redraw(self) -> None:
        self.delete("all")
        self._draw_selection_overlay()
        self._recompute_note_positions()
        self._draw_staff()
        self._draw_notes()
        
        
    def _draw_staff(self) -> None:
        """Draw the 5 staff lines + barlines + beat grid + clef + time signature."""
        width, height, top_line_y, bottom_line_y, line_spacing = self._compute_staff_geometry()
        cfg = self.style
        self._recompute_note_positions()
        # Staff horizontal span
        inner_total = self._content_width - self.right_margin - self.left_margin
        info_w = self.info_width
        usable_width = max(0.0, inner_total - info_w)

        measures = self.score.measures
        num_measures = len(measures)


        # --- horizontal staff lines ---
        for i in range(5):
            y = top_line_y + i * line_spacing
            self.create_line(
                self.left_margin,
                y,
                self.left_margin + self.info_width + self.measure_width * num_measures,
                y,
                fill=cfg.staff_line_color,
                width=cfg.staff_line_width,
            )

        # --- clef + time sig in the info area ---
        self._draw_clef_and_time_signature(top_line_y, line_spacing)

        # --- barlines + beat grid (if we have a score) ---
        if self.score is None or not self.score.measures:
            return

        if num_measures <= 0 or usable_width <= 0:
            return

        measure_width = usable_width / num_measures
        beats_per_bar = self.get_beats_per_bar()
        # Draw barlines (between measures and at the end)
        for mi in range(num_measures + 1):
            x_bar = self.left_margin + info_w + mi * self.measure_width
            self.create_line(
                x_bar,
                top_line_y,
                x_bar,
                bottom_line_y,
                fill=cfg.barline_color,
                width=cfg.barline_width,
            )

        # Draw light beat grid inside each measure
        if beats_per_bar > 0:
            for mi in range(num_measures):
                measure_start_x = self.left_margin + info_w + mi * self.measure_width
                for b in range(1, beats_per_bar):
                    t = b / beats_per_bar
                    x = measure_start_x + t * self.measure_width
                    self.create_line(
                        x,
                        top_line_y,
                        x,
                        bottom_line_y,
                        fill=cfg.beat_grid_color,
                        width=cfg.beat_grid_width,
                        dash=(2, 4),
                    )

    def _draw_selection_overlay(self) -> None:
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
        beats_per_bar = self.get_beats_per_bar()

        measure_width = beats_per_bar * self.px_per_beat
        measure_start_x = self.left_margin + self.info_width + measure_index * measure_width


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

        y0 = self.top_margin - 5
        y1 = height - self.bottom_margin + 5

        self.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=self.style.selection_fill,
            outline="",
        )

    # ===== Graphical helpers for note appearance =================

    def _draw_notes(self) -> None:
        """
        Draw noteheads, stems and beams using the flattened arrays computed in
        _recompute_note_positions().
        """
        if not self.note_positions:
            return

        # Make sure geometry cache is up-to-date
        self._compute_staff_geometry()

        ctx = NoteDrawingContext(
            canvas=self,
            style=self.style,
            line_spacing=self._line_spacing,
            middle_line_y=self._middle_line_y,
        )

        n = len(self.note_positions)

        # First pass: gather per-note drawing info.
        note_info = []
        for idx in range(n):
            x, y = self.note_positions[idx]
            beats = (
                self._note_duration_beats[idx]
                if idx < len(self._note_duration_beats)
                else 1.0
            )
            kind = duration_kind_from_beats(beats)
            filled = is_filled_notehead(kind)
            beams = beams_for_kind(kind)
            measure_index = (
                self._note_measure_index[idx]
                if idx < len(self._note_measure_index)
                else 0
            )
            step = self._note_step[idx] if idx < len(self._note_step) else 0

            # Stem direction: notes on or below middle line -> stem up,
            # notes above middle line -> stem down.
            # step > 0 means above B4 (our reference at middle line).
            stem_dir: StemDirection = "down" if step > 0 else "up"

            note_info.append(
                {
                    "idx": idx,
                    "x": x,
                    "y": y,
                    "kind": kind,
                    "filled": filled,
                    "beams": beams,
                    "beamable": is_beamable(kind),
                    "measure_index": measure_index,
                    "stem_dir": stem_dir,
                    "highlight": (idx == self.highlight_index),
                }
            )

        # Second pass: draw noteheads and stems, record stem tip positions
        # for potential beams.
        stem_tips: Dict[int, Tuple[float, float]] = {}

        for info in note_info:
            idx = info["idx"]
            x = info["x"]
            y = info["y"]
            filled = info["filled"]
            stem_dir = info["stem_dir"]
            kind = info["kind"]
            highlight = info["highlight"]

            # Notehead
            draw_notehead(
                ctx,
                x,
                y,
                filled=filled,
                highlighted=highlight,
            )

            # Stems: whole notes don't have stems; others do.
            if kind != "whole":
                tip_x, tip_y = draw_stem(ctx, x, y, stem_dir)
                stem_tips[idx] = (tip_x, tip_y)

        # Third pass: build simple beam groups and draw beams.
        current_group: List[Dict] = []

        def flush_group() -> None:
            if len(current_group) < 2:
                return
            # Smallest beam count wins (so mix of 8th/16th gets at least one beam).
            group_beams = min(info["beams"] for info in current_group)
            if group_beams <= 0:
                return

            # All group notes have the same stem direction by construction.
            direction: StemDirection = current_group[0]["stem_dir"]

            # Collect stem tips in visual order.
            tips: List[Tuple[float, float]] = []
            for info in current_group:
                tip = stem_tips.get(info["idx"])
                if tip is not None:
                    tips.append(tip)

            if len(tips) >= 2:
                draw_beam_group(ctx, tips, direction, group_beams)

        last_measure = None
        last_stem_dir: Optional[StemDirection] = None

        for info in note_info:
            if info["beamable"]:
                same_measure = (
                    last_measure is None
                    or info["measure_index"] == last_measure
                )
                same_direction = (
                    last_stem_dir is None
                    or info["stem_dir"] == last_stem_dir
                )

                if current_group and (not same_measure or not same_direction):
                    # Beam group broken by measure or stem direction change.
                    flush_group()
                    current_group = []

                current_group.append(info)
                last_measure = info["measure_index"]
                last_stem_dir = info["stem_dir"]
            else:
                # Non-beamable note breaks any ongoing group.
                if current_group:
                    flush_group()
                    current_group = []
                    last_measure = None
                    last_stem_dir = None

        # Flush trailing group
        if current_group:
            flush_group()

    def _draw_treble_clef_image(
        self,
        top_line_y: float,
        line_spacing: float,
    ) -> bool:
        """
        Try to draw the treble clef from assets/treble_clef.png.
        Returns True on success, False if we should fall back to vector/glyph.
        """
        if Image is None or ImageTk is None:
            return False

        # Lazy-load original image
        if self._clef_image is None:
            try:
                self._clef_image = Image.open("assets/treble_clef.png")
            except Exception:
                return False

        # Scale image to staff height
        staff_height = 4 * line_spacing
        target_h = int(staff_height * 1.2)
        if target_h <= 0:
            target_h = 10

        w, h = self._clef_image.size
        scale = target_h / float(h)
        target_w = max(1, int(w * scale))

        img_resized = self._clef_image.resize((target_w, target_h), Image.LANCZOS)
        self._clef_photo = ImageTk.PhotoImage(img_resized)

        x = self.left_margin + self.info_width * 0.3
        y = top_line_y + 2 * line_spacing  # around middle of staff

        self.create_image(x, y, image=self._clef_photo)
        return True

    def _draw_clef_and_time_signature(
        self,
        top_line_y: float,
        line_spacing: float,
    ) -> None:
        """
        Draw treble clef + time signature inside the info region, before the first barline.
        """
        ctx = NoteDrawingContext(
            canvas=self,
            style=self.style,
            line_spacing=line_spacing,
            middle_line_y=self._middle_line_y,
        )

        info_w = self.info_width

        # 1) Clef: try image, fall back to glyph
        drew_image = self._draw_treble_clef_image(top_line_y, line_spacing)
        if not drew_image:
            clef_x = self.left_margin + info_w * 0.3
            draw_treble_clef(ctx, clef_x, top_line_y, line_spacing)

        # 2) Time signature (if available)
        if self.score is not None and self.score.time_signature:
            num, den = self.score.time_signature
            ts_x = self.left_margin + info_w * 0.75
            draw_time_signature(ctx, ts_x, top_line_y, line_spacing, num, den)
