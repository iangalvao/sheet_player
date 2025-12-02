# ui/staff_view_core.py
from __future__ import annotations

from typing import List, Tuple, Optional, Dict, Any

from domain.score import Score
from domain.notation import (
    NotatedScore,
    NotatedAtom,
    notated_duration_to_beats,
    build_notated_score,
)

from notation.style_config import StyleConfig
from notation.formatting import (
    DurationFormatter,
    StaffLayoutConfig,
    HorizontalLayout,
    PitchMapper,
)
from notation.drawing import (
    NoteDrawingContext,
    NotePainter,
    StemDirection,
)
from ui.canvas_api import CanvasAPI


class StaffViewCore:
    """
    Toolkit-agnostic staff renderer.

    Depends only on CanvasAPI and notation/domain types.
    """

    def __init__(
        self,
        canvas: CanvasAPI,
        style: Optional[StyleConfig] = None,
        layout_cfg: Optional[StaffLayoutConfig] = None,
        duration_formatter: Optional[DurationFormatter] = None,
        horizontal_layout: Optional[HorizontalLayout] = None,
        pitch_mapper: Optional[PitchMapper] = None,
    ) -> None:
        self.canvas = canvas

        self.style = style or StyleConfig()
        self.layout_cfg = layout_cfg or StaffLayoutConfig()
        self.duration_formatter = duration_formatter or DurationFormatter()
        self.horizontal_layout = horizontal_layout or HorizontalLayout()
        self.pitch_mapper = pitch_mapper or PitchMapper(ref_pitch="B4")

        # External source of truth
        self.score: Optional[Score] = None
        self._notated_score: Optional[NotatedScore] = None

        # Flattened note visuals (positions + basic meta)
        self.note_positions: List[Tuple[float, float]] = []
        self.note_atoms: List[Optional[NotatedAtom]] = []
        self._note_measure_index: List[int] = []
        self._note_duration_beats: List[float] = []
        self._note_step: List[int] = []
        self._note_pitch: List[str] = []
        # Cached drawing properties per note (precomputed in _recompute_note_positions)
        self._note_kind: List[str] = []
        self._note_filled: List[bool] = []
        self._note_beams: List[int] = []
        self._note_beamable: List[bool] = []
        self._note_stem_dir: List[StemDirection] = []

        # Interaction state
        self.highlight_index: int = -1
        self.selection_region: Optional[Tuple[int, float, float]] = None

        # Highlight overlay canvas item
        self._highlight_item: Optional[Any] = None

        # Geometry cache
        self._line_spacing: float = 0.0
        self._middle_line_y: float = 0.0

        # Horizontal layout & scrolling
        self.measure_width: float = 90.0
        self._content_width: int = self.canvas.get_width()

    # ===== External API (IStaffView-like) ===============================

    def set_score(self, score: Score) -> None:
        self.score = score
        self._notated_score = build_notated_score(score)
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def set_notated_score(self, nscore: NotatedScore) -> None:
        self._notated_score = nscore
        self.highlight_index = -1
        self.selection_region = None
        self._recompute_note_positions()
        self._redraw()

    def highlight_note(self, index: int) -> None:
        """
        Update highlight index and move a lightweight overlay.
        No full redraw here to avoid blocking the Tk mainloop.
        """
        # Normalize/validate index
        if (self.score is None and self._notated_score is None) or not self.note_positions:
            index = -1
        elif index < 0 or index >= len(self.note_positions):
            index = -1

        # If nothing changed, do nothing
        if index == self.highlight_index:
            return

        self.highlight_index = index
        self._update_highlight_overlay()

    def set_selection_region(
        self,
        measure_index: int,
        beat_start: float,
        beat_end: float,
    ) -> None:
        self.selection_region = (measure_index, beat_start, beat_end)
        self._redraw()

    def scroll_to_note(self, index: int, margin: float = 80.0) -> None:
        if index < 0 or index >= len(self.note_positions):
            return

        content_width = max(self._content_width, 1)
        visible_width = self.canvas.get_width()

        if visible_width >= content_width:
            return

        x, _ = self.note_positions[index]

        first_frac, last_frac = self.canvas.xview()
        first_x = first_frac * content_width
        last_x = last_frac * content_width

        if first_x + margin <= x <= last_x - margin:
            return

        new_first_x = x - visible_width / 2.0
        new_first_x = max(0.0, min(new_first_x, content_width - visible_width))
        new_first_frac = new_first_x / content_width
        self.canvas.xview_moveto(new_first_frac)

    # ===== Geometry helpers =============================================

    def _compute_staff_geometry(self) -> Tuple[int, int, float, float, float]:
        width = self.canvas.get_width()
        height = self.canvas.get_height()

        cfg = self.layout_cfg
        staff_height = height - cfg.top_margin - cfg.bottom_margin
        line_spacing = staff_height / 4.0  # 4 gaps between 5 lines
        top_line_y = cfg.top_margin
        bottom_line_y = top_line_y + 4 * line_spacing

        self._line_spacing = line_spacing
        self._middle_line_y = top_line_y + 2 * line_spacing

        return width, height, top_line_y, bottom_line_y, line_spacing

    def _get_beats_per_bar(self) -> float:
        if self.score and self.score.time_signature:
            beats_per_bar = self.score.time_signature[0]
            if beats_per_bar > 0:
                return float(beats_per_bar)
        return 4.0

    # ===== Layout & drawing =============================================

    def _recompute_note_positions(self) -> None:
        # Base arrays
        self.note_positions = []
        self.note_atoms = []
        self._note_measure_index = []
        self._note_duration_beats = []
        self._note_step = []

        # Cached draw properties
        self._note_kind = []
        self._note_filled = []
        self._note_beams = []
        self._note_beamable = []
        self._note_stem_dir = []
        self._note_pitch = []

        width, height, _, _, line_spacing = self._compute_staff_geometry()
        half_step = line_spacing / 2.0
        middle_line_y = self._middle_line_y

        cfg = self.layout_cfg
        beats_per_bar = self._get_beats_per_bar()

        measure_width = self.horizontal_layout.measure_width(beats_per_bar, cfg)
        self.measure_width = measure_width

        # ---- Preferred: NotatedScore path -------------------------
        if self._notated_score is not None:
            nscore = self._notated_score
            measures = nscore.measures
            if not measures:
                self._content_width = width
                self.canvas.config(scrollregion=(0, 0, self._content_width, height))
                return

            for m in measures:
                measure_index = m.index
                for atom in m.atoms:
                    beat_start = atom.beat_start.to_float()
                    dur_beats = notated_duration_to_beats(atom.duration, m.time_signature)

                    x = self.horizontal_layout.note_center_x(
                        measure_index,
                        beat_start,
                        dur_beats,
                        beats_per_bar,
                        cfg,
                    )

                    step = self.pitch_mapper.step_from_pitch(atom.pitch)
                    y = middle_line_y - step * half_step

                    # Base arrays
                    self.note_positions.append((x, y))
                    self.note_atoms.append(atom)
                    self._note_measure_index.append(measure_index)
                    self._note_duration_beats.append(dur_beats)
                    self._note_step.append(step)
                    self._note_pitch.append(atom.pitch)
                    # Cached draw properties
                    kind = self.duration_formatter.classify(dur_beats)
                    filled = self.duration_formatter.is_filled(kind)
                    beams = self.duration_formatter.beam_count(kind)
                    beamable = self.duration_formatter.is_beamable(kind)
                    stem_dir: StemDirection = "down" if step > 0 else "up"

                    self._note_kind.append(kind)
                    self._note_filled.append(filled)
                    self._note_beams.append(beams)
                    self._note_beamable.append(beamable)
                    self._note_stem_dir.append(stem_dir)

            num_measures = len(measures)
            self._content_width = int(
                cfg.left_margin
                + cfg.info_region_width
                + num_measures * measure_width
                + cfg.right_margin
            )
            self.canvas.config(scrollregion=(0, 0, self._content_width, height))
            return

        # ---- Fallback: raw Score path -----------------------------
        if self.score is None:
            self._content_width = width
            self.canvas.config(scrollregion=(0, 0, self._content_width, height))
            return

        measures = self.score.measures
        if not measures:
            self._content_width = width
            self.canvas.config(scrollregion=(0, 0, self._content_width, height))
            return

        for mi, measure in enumerate(measures):
            beat_pos = 0.0
            for note in measure.notes:
                dur_beats = note.duration_beats
                x = self.horizontal_layout.note_center_x(
                    mi,
                    beat_pos,
                    dur_beats,
                    beats_per_bar,
                    cfg,
                )
                step = self.pitch_mapper.step_from_pitch(note.pitch)
                y = middle_line_y - step * half_step

                # Base arrays
                self.note_positions.append((x, y))
                self.note_atoms.append(None)
                self._note_measure_index.append(mi)
                self._note_duration_beats.append(dur_beats)
                self._note_step.append(step)

                # Cached draw properties
                kind = self.duration_formatter.classify(dur_beats)
                filled = self.duration_formatter.is_filled(kind)
                beams = self.duration_formatter.beam_count(kind)
                beamable = self.duration_formatter.is_beamable(kind)
                stem_dir: StemDirection = "down" if step > 0 else "up"

                self._note_kind.append(kind)
                self._note_filled.append(filled)
                self._note_beams.append(beams)
                self._note_beamable.append(beamable)
                self._note_stem_dir.append(stem_dir)
                self._note_pitch.append(note.pitch)
                
                beat_pos += dur_beats

        num_measures = len(measures)
        self._content_width = int(
            cfg.left_margin
            + cfg.info_region_width
            + num_measures * measure_width
            + cfg.right_margin
        )
        self.canvas.config(scrollregion=(0, 0, self._content_width, height))

    def _redraw(self) -> None:
        self.canvas.delete("all")
        # original order: selection → staff → notes
        self._draw_selection_overlay()
        self._draw_staff()
        self._draw_notes()
        self._update_highlight_overlay()

    # ===== Highlight overlay ============================================

    def _accidental_from_pitch(self, pitch: str) -> Optional[str]:
        """
        Very naive pitch parser:
          - 'C#4' -> 'sharp'
          - 'Bb4' -> 'flat'
          - otherwise -> None (no explicit accidental drawn)
        """
        # Avoid octave digits
        core = pitch[:-1] if pitch and pitch[-1].isdigit() else pitch
        if "#" in core:
            return "sharp"
        if "b" in core:
            return "flat"
        # Later we might draw naturals where needed based on key signature
        return None


    # ===== Highlight overlay ============================================

    def _update_highlight_overlay(self) -> None:
        """
        Draw/move a small overlay around the current note, without
        redrawing the entire staff.
        """
        # Remove previous overlay if any
        if self._highlight_item is not None:
            self.canvas.delete(self._highlight_item)
            self._highlight_item = None

        if self.highlight_index < 0 or self.highlight_index >= len(self.note_positions):
            return

        x, y = self.note_positions[self.highlight_index]
        cfg = self.style

        # Slightly bigger than the notehead
        rx = cfg.note_radius_x * 1.3
        ry = cfg.note_radius_y * 1.3

        self._highlight_item = self.canvas.create_rectangle(
            x - rx,
            y - ry,
            x + rx,
            y + ry,
            outline=cfg.fill_highlight,
            width=2.0,
        )

    # ===== Staff, selection, notes ======================================

    def _draw_staff(self) -> None:
        _, _, top_line_y, bottom_line_y, line_spacing = self._compute_staff_geometry()
        cfg = self.layout_cfg
        style = self.style

        # Determine number of measures
        num_measures = 0
        if self._notated_score is not None:
            num_measures = len(self._notated_score.measures)
        elif self.score is not None:
            num_measures = len(self.score.measures)

        # Staff lines
        for i in range(5):
            y = top_line_y + i * line_spacing
            self.canvas.create_line(
                cfg.left_margin,
                y,
                cfg.left_margin + cfg.info_region_width + self.measure_width * num_measures,
                y,
                fill=style.staff_line_color,
                width=style.staff_line_width,
            )

        # Clef + time signature
        self._draw_clef_and_time_signature(top_line_y, line_spacing)

        if self.score is None or not self.score.measures or num_measures <= 0:
            return

        beats_per_bar = self._get_beats_per_bar()

        # Measure barlines
        for mi in range(num_measures + 1):
            x_bar = cfg.left_margin + cfg.info_region_width + mi * self.measure_width
            self.canvas.create_line(
                x_bar,
                top_line_y,
                x_bar,
                bottom_line_y,
                fill=style.barline_color,
                width=style.barline_width,
            )

        # Light beat grid
        if beats_per_bar > 0:
            for mi in range(num_measures):
                measure_start_x = cfg.left_margin + cfg.info_region_width + mi * self.measure_width
                for b in range(1, int(beats_per_bar)):
                    t = b / beats_per_bar
                    x = measure_start_x + t * self.measure_width
                    self.canvas.create_line(
                        x,
                        top_line_y,
                        x,
                        bottom_line_y,
                        fill=style.beat_grid_color,
                        width=style.beat_grid_width,
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

        height = self.canvas.get_height()
        cfg = self.layout_cfg
        beats_per_bar = self._get_beats_per_bar()

        measure_start_x = cfg.left_margin + cfg.info_region_width + measure_index * self.measure_width

        bs = max(0.0, beat_start)
        be = max(bs, beat_end)
        max_be = float(beats_per_bar)
        if bs > max_be:
            return
        be = min(be, max_be)

        t0 = bs / beats_per_bar
        t1 = be / beats_per_bar
        x0 = measure_start_x + t0 * self.measure_width
        x1 = measure_start_x + t1 * self.measure_width

        y0 = cfg.top_margin - 5
        y1 = height - cfg.bottom_margin + 5

        self.canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            fill=self.style.selection_fill,
            outline="",
        )

    def _draw_notes(self) -> None:
        if not self.note_positions:
            return

        # ensure geometry is up-to-date
        _, _, _, _, line_spacing = self._compute_staff_geometry()

        ctx = NoteDrawingContext(
            canvas=self.canvas,
            style=self.style,
            line_spacing=line_spacing,
            middle_line_y=self._middle_line_y,
        )
        painter = NotePainter(ctx)

        n = len(self.note_positions)

        # First pass: lightweight info (all heavy computation is pre-cached)
        note_info: List[Dict[str, Any]] = []
        for idx in range(n):
            x, y = self.note_positions[idx]
            kind = self._note_kind[idx]
            filled = self._note_filled[idx]
            beams = self._note_beams[idx]
            beamable = self._note_beamable[idx]
            measure_index = self._note_measure_index[idx]
            stem_dir = self._note_stem_dir[idx]
            highlight = (idx == self.highlight_index)

            note_info.append(
                {
                    "idx": idx,
                    "x": x,
                    "y": y,
                    "kind": kind,
                    "filled": filled,
                    "beams": beams,
                    "beamable": beamable,
                    "measure_index": measure_index,
                    "stem_dir": stem_dir,
                    "highlight": highlight,
                }
            )

        # Second pass: noteheads + stems
        stem_tips: Dict[int, Tuple[float, float]] = {}

        for info in note_info:
            idx = info["idx"]
            x = info["x"]
            y = info["y"]
            filled = info["filled"]
            stem_dir = info["stem_dir"]
            kind = info["kind"]
            highlight = info["highlight"]

            # 1) Ledger lines (for out-of-staff notes)
            step = self._note_step[idx] if idx < len(self._note_step) else 0
            painter.draw_ledger_lines(x, step)

            # 2) Accidentals (if any)
            if idx < len(self._note_pitch):
                pitch = self._note_pitch[idx]
                acc = self._accidental_from_pitch(pitch)
                if acc is not None:
                    # Shift accidental a bit to the left of the note
                    x_acc = x - (self.style.note_radius_x + self.style.accidental_x_offset)
                    painter.draw_accidental(x_acc, y, acc)

            # 3) Notehead
            painter.draw_notehead(
                x,
                y,
                filled=filled,
                highlighted=highlight,
            )

            # 4) Stem
            if kind != "whole":
                tip_x, tip_y = painter.draw_stem(x, y, stem_dir)
                stem_tips[idx] = (tip_x, tip_y)

        # Third pass: beam groups
        current_group: List[Dict[str, Any]] = []

        def flush_group() -> None:
            if len(current_group) < 2:
                return
            group_beams = min(info["beams"] for info in current_group)
            if group_beams <= 0:
                return

            direction: StemDirection = current_group[0]["stem_dir"]
            tips: List[Tuple[float, float]] = []
            for info in current_group:
                tip = stem_tips.get(info["idx"])
                if tip is not None:
                    tips.append(tip)

            if len(tips) >= 2:
                painter.draw_beam_group(tips, direction, group_beams)

        last_measure: Optional[int] = None
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
                    flush_group()
                    current_group = []

                current_group.append(info)
                last_measure = info["measure_index"]
                last_stem_dir = info["stem_dir"]
            else:
                if current_group:
                    flush_group()
                    current_group = []
                    last_measure = None
                    last_stem_dir = None

        if current_group:
            flush_group()

    # ---- Clef & time signature ----------------------------------------

    def _draw_clef_and_time_signature(
        self,
        top_line_y: float,
        line_spacing: float,
    ) -> None:
        ctx = NoteDrawingContext(
            canvas=self.canvas,
            style=self.style,
            line_spacing=line_spacing,
            middle_line_y=self._middle_line_y,
        )
        painter = NotePainter(ctx)

        cfg = self.layout_cfg
        info_w = cfg.info_region_width

        # Clef
        clef_x = cfg.left_margin + info_w * 0.3
        painter.draw_treble_clef(clef_x, top_line_y)

        # Time signature
        if self.score is not None and self.score.time_signature:
            num, den = self.score.time_signature
            ts_x = cfg.left_margin + info_w * 0.75
            painter.draw_time_signature(ts_x, top_line_y, num, den)
