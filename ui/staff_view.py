# ui/staff_view.py
from __future__ import annotations

import tkinter as tk

from domain.score import Score
from domain.notation import NotatedScore

from notation.style_config import StyleConfig
from notation.formatting import StaffLayoutConfig, DurationFormatter, HorizontalLayout, PitchMapper
from ui.canvas_api import CanvasAPI
from ui.tk_canvas_adapter import TkCanvasAdapter
from ui.staff_view_core import StaffViewCore


class StaffViewTk:
    """
    Tk-specific wrapper around StaffViewCore.

    Owns a tk.Canvas, adapts it to CanvasAPI, and exposes the same
    high-level methods (set_score, highlight_note, etc.).
    """

    def __init__(
        self,
        master,
        width: int = 800,
        height: int = 160,
        style: StyleConfig | None = None,
        layout_cfg: StaffLayoutConfig | None = None,
        **kwargs,
    ) -> None:
        self.canvas = tk.Canvas(master, width=width, height=height, bg="white", **kwargs)
        adapter: CanvasAPI = TkCanvasAdapter(self.canvas)

        self._core = StaffViewCore(
            canvas=adapter,
            style=style,
            layout_cfg=layout_cfg,
            duration_formatter=DurationFormatter(),
            horizontal_layout=HorizontalLayout(),
            pitch_mapper=PitchMapper(ref_pitch="B4"),
        )

    # --- expose widget for layout --------------------------------

    def get_widget(self) -> tk.Canvas:
        return self.canvas

    # --- High-level API (IStaffView) ------------------------------

    def set_score(self, score: Score) -> None:
        self._core.set_score(score)

    def set_notated_score(self, nscore: NotatedScore) -> None:
        self._core.set_notated_score(nscore)

    def highlight_note(self, index: int) -> None:
        self._core.highlight_note(index)

    def set_selection_region(
        self,
        measure_index: int,
        beat_start: float,
        beat_end: float,
    ) -> None:
        self._core.set_selection_region(measure_index, beat_start, beat_end)

    def scroll_to_note(self, index: int, margin: float = 80.0) -> None:
        self._core.scroll_to_note(index, margin=margin)

    @property
    def core(self) -> StaffViewCore:
        """Access underlying core (for testing / advanced usage)."""
        return self._core

    # --- Backwards-friendly: delegate missing attrs to canvas -----

    def __getattr__(self, name: str):
        """
        If an attribute is not found on StaffViewTk, delegate to the
        underlying tk.Canvas. This lets existing code do:

            self.staff_view = StaffView(...)
            self.staff_view.pack(...)
            self.staff_view.bind("<Button-1>", ...)
        """
        return getattr(self.canvas, name)


# Optional: keep old name for now so existing imports still work:
# from ui.staff_view import StaffView
StaffView = StaffViewTk
