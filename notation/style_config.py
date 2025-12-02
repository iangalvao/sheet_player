# notation/style_config.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass
class StyleConfig:
    """
    Central configuration for staff drawing styles.
    """
    # Notehead geometry
    note_radius_x: float = 6.0
    note_radius_y: float = 4.0

    # Stems
    stem_length: float = 36.0
    stem_width: float = 1.9

    # Beams
    beam_thickness: float = 5.0
    beam_spacing: float = 9.0  # distance between multiple beams (16th, 32nd, ...)

    # Colors
    fill_quarter_and_shorter: str = "black"
    fill_half_and_whole: str = "white"
    fill_highlight: str = "deepskyblue"
    outline: str = "black"

    # Staff / grid strokes
    staff_line_width: float = 1.5
    barline_width: float = 1.9
    beat_grid_width: float = 1.0

    staff_line_color: str = "black"
    barline_color: str = "#444444"
    beat_grid_color: str = "#bbbbbb"

    selection_fill: str = "#ffd8d8"

    # Clef / time-signature region
    info_region_width: float = 90.0

    # NEW: ledger lines
    ledger_line_width: float = 1.2
    ledger_line_length: float = 16.0  # visual half-length each side from note center

    # NEW: accidentals
    accidental_font_scale: float = 0.4  # relative to note size
    accidental_x_offset: float = 7.0   # shift accidentals to the left of note
