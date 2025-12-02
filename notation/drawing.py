# notation/drawing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Literal

from notation.style_config import StyleConfig
from ui.canvas_api import CanvasAPI  # depends on abstract canvas, not Tk


StemDirection = Literal["up", "down"]


@dataclass
class NoteDrawingContext:
    """
    Lightweight container with all info drawing helpers need.

    Keeps the primitives decoupled from StaffView internals.
    """
    canvas: CanvasAPI
    style: StyleConfig
    line_spacing: float
    middle_line_y: float  # y position of the middle staff line


class NotePainter:
    """
    Collection of drawing primitives for notes, beams, clef, time signature.
    """

    def __init__(self, ctx: NoteDrawingContext) -> None:
        self.ctx = ctx

    # --- Noteheads & stems ----------------------------------------

    def draw_notehead(
        self,
        x: float,
        y: float,
        *,
        filled: bool,
        highlighted: bool,
    ) -> None:
        cfg = self.ctx.style

        if highlighted:
            fill_color = cfg.fill_highlight
        else:
            fill_color = (
                cfg.fill_quarter_and_shorter if filled else cfg.fill_half_and_whole
            )

        self.ctx.canvas.create_rectangle(  # will update to oval-like visuals later if needed
            x - cfg.note_radius_x,
            y - cfg.note_radius_y,
            x + cfg.note_radius_x,
            y + cfg.note_radius_y,
            fill=fill_color,
            outline=cfg.outline,
            width=1.2,
        )

    def draw_stem(
        self,
        x: float,
        y: float,
        direction: StemDirection,
    ) -> Tuple[float, float]:
        cfg = self.ctx.style

        if direction == "up":
            x_stem = x + cfg.note_radius_x
            y_base = y
            y_tip = y_base - cfg.stem_length
        else:  # "down"
            x_stem = x - cfg.note_radius_x
            y_base = y
            y_tip = y_base + cfg.stem_length

        self.ctx.canvas.create_line(
            x_stem,
            y_base,
            x_stem,
            y_tip,
            width=cfg.stem_width,
            fill=cfg.outline,
        )

        return x_stem, y_tip

    def draw_beam_group(
        self,
        stem_tips: List[Tuple[float, float]],
        direction: StemDirection,
        beams: int,
    ) -> None:
        if beams <= 0 or len(stem_tips) < 2:
            return

        cfg = self.ctx.style

        x0, y0 = stem_tips[0]
        x1, y1 = stem_tips[-1]

        # For "up" stems beams go slightly below the tip, for "down" slightly above.
        sign = 1.0 if direction == "down" else -1.0

        for i in range(beams):
            offset = sign * i * cfg.beam_spacing
            self.ctx.canvas.create_line(
                x0,
                y0 + offset,
                x1,
                y1 + offset,
                width=cfg.beam_thickness,
                fill=cfg.fill_quarter_and_shorter,
                capstyle="projecting",  # Tk will understand this; other backends can ignore
            )

    # --- Clef & time signature ------------------------------------

    def draw_treble_clef(
        self,
        x: float,
        top_line_y: float,
    ) -> None:
        """
        Simple treble clef using the Unicode glyph, sized to staff.

        Backends that want SVG/PNG can override or extend this at a higher level.
        """
        line_spacing = self.ctx.line_spacing
        y_center = top_line_y + 2 * line_spacing

        font_size = int(line_spacing * 3.0)
        if font_size < 10:
            font_size = 10

        self.ctx.canvas.create_text(
            x,
            y_center,
            text="𝄞",
            font=("DejaVu Sans", font_size),
            fill=self.ctx.style.outline,
        )

    def draw_time_signature(
        self,
        x: float,
        top_line_y: float,
        numerator: int,
        denominator: int,
    ) -> None:
        line_spacing = self.ctx.line_spacing

        y_num = top_line_y + 1.2 * line_spacing
        y_den = top_line_y + 2.8 * line_spacing

        font_size = int(line_spacing * 1.8)
        if font_size < 8:
            font_size = 8

        font = ("DejaVu Sans", font_size)

        self.ctx.canvas.create_text(
            x,
            y_num,
            text=str(numerator),
            font=font,
            fill=self.ctx.style.outline,
        )
        self.ctx.canvas.create_text(
            x,
            y_den,
            text=str(denominator),
            font=font,
            fill=self.ctx.style.outline,
        )
