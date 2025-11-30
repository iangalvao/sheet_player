# ui/style_config.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StyleConfig:
    """
    Central configuration for staff drawing styles.

    You can evolve this over time (ledger lines, rests, slurs/ties, fonts, etc.)
    without touching the rest of the drawing logic too much.
    """
    # Notehead geometry
    note_radius_x: float = 6.0
    note_radius_y: float = 4.0

    # Stems
    stem_length: float = 36.0
    stem_width: float = 1.4

    # Beams
    beam_thickness: float = 3.0
    beam_spacing: float = 5.0  # distance between multiple beams (16th, 32nd, ...)

    # Colors
    fill_quarter_and_shorter: str = "black"
    fill_half_and_whole: str = "white"
    fill_highlight: str = "deepskyblue"
    outline: str = "black"

    # Staff / grid strokes
    staff_line_width: float = 1.2
    barline_width: float = 1.2
    beat_grid_width: float = 1.0

    staff_line_color: str = "black"
    barline_color: str = "#444444"
    beat_grid_color: str = "#dddddd"

    selection_fill: str = "#ffd8d8"
