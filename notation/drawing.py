# notation/drawing.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Literal

import tkinter as tk

from notation.style_config import StyleConfig


StemDirection = Literal["up", "down"]


@dataclass
class NoteDrawingContext:
    """
    Lightweight container with all info drawing helpers need.

    Keeps the primitives decoupled from StaffView internals.
    """
    canvas: tk.Canvas
    style: StyleConfig
    line_spacing: float
    middle_line_y: float  # y position of the middle staff line


def draw_notehead(
    ctx: NoteDrawingContext,
    x: float,
    y: float,
    *,
    filled: bool,
    highlighted: bool,
) -> None:
    """
    Draw an oval notehead at (x, y). For now, we use simple ellipses;
    this could be replaced by a slanted polygon later.
    """
    cfg = ctx.style

    if highlighted:
        fill_color = cfg.fill_highlight
    else:
        fill_color = cfg.fill_quarter_and_shorter if filled else cfg.fill_half_and_whole

    ctx.canvas.create_oval(
        x - cfg.note_radius_x,
        y - cfg.note_radius_y,
        x + cfg.note_radius_x,
        y + cfg.note_radius_y,
        fill=fill_color,
        outline=cfg.outline,
        width=1.2,
    )


def draw_stem(
    ctx: NoteDrawingContext,
    x: float,
    y: float,
    direction: StemDirection,
) -> Tuple[float, float]:
    """
    Draw a vertical stem attached to the notehead at (x, y).

    Returns (x_tip, y_tip) where the stem ends, so beams can connect there.
    """
    cfg = ctx.style

    # Attach stems slightly to the right or left side of the notehead.
    if direction == "up":
        x_stem = x + cfg.note_radius_x
        y_base = y
        y_tip = y_base - cfg.stem_length
    else:  # "down"
        x_stem = x - cfg.note_radius_x
        y_base = y
        y_tip = y_base + cfg.stem_length

    ctx.canvas.create_line(
        x_stem,
        y_base,
        x_stem,
        y_tip,
        width=cfg.stem_width,
        fill=cfg.outline,
    )

    return x_stem, y_tip


def draw_beam_group(
    ctx: NoteDrawingContext,
    stem_tips: List[Tuple[float, float]],
    direction: StemDirection,
    beams: int,
) -> None:
    """
    Draw simple horizontal/slanted beams connecting the given stem tips.

    - `stem_tips` should be in visual order (left to right).
    - `beams` is the number of parallel beams to draw (1 for 8th, 2 for 16th).
    """
    if beams <= 0 or len(stem_tips) < 2:
        return

    cfg = ctx.style

    # We'll connect only the first and last stem tip with a straight line,
    # then draw additional beams offset by beam_spacing.
    x0, y0 = stem_tips[0]
    x1, y1 = stem_tips[-1]

    # Direction-based offset: for "up" stems beams go slightly below the tip,
    # for "down" stems they go slightly above.
    sign = 1.0 if direction == "down" else -1.0

    for i in range(beams):
        offset = sign * i * cfg.beam_spacing
        ctx.canvas.create_line(
            x0,
            y0 + offset,
            x1,
            y1 + offset,
            width=cfg.beam_thickness,
            fill=cfg.fill_quarter_and_shorter,
            capstyle=tk.PROJECTING,
        )
