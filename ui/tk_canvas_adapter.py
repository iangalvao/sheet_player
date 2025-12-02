# ui/tk_canvas_adapter.py
from __future__ import annotations

from typing import Any, Tuple
import tkinter as tk

from ui.canvas_api import CanvasAPI


class TkCanvasAdapter(CanvasAPI):
    """
    Adapts a tk.Canvas to the CanvasAPI interface.
    """

    def __init__(self, canvas: tk.Canvas) -> None:
        self._c = canvas

    # Geometry
    def get_width(self) -> int:
        return int(self._c["width"])

    def get_height(self) -> int:
        return int(self._c["height"])

    # Config
    def config(self, **kwargs: Any) -> None:
        self._c.config(**kwargs)

    # Drawing
    def create_line(self, x1, y1, x2, y2, **kwargs: Any) -> Any:
        return self._c.create_line(x1, y1, x2, y2, **kwargs)

    def create_rectangle(self, x1, y1, x2, y2, **kwargs: Any) -> Any:
        return self._c.create_rectangle(x1, y1, x2, y2, **kwargs)

    def create_image(self, x, y, **kwargs: Any) -> Any:
        return self._c.create_image(x, y, **kwargs)

    def create_text(self, x, y, **kwargs: Any) -> Any:
        return self._c.create_text(x, y, **kwargs)

    # Housekeeping
    def delete(self, what: Any) -> None:
        self._c.delete(what)

    # Scrolling
    def xview(self) -> Tuple[float, float]:
        return self._c.xview()

    def xview_moveto(self, fraction: float) -> None:
        self._c.xview_moveto(fraction)

    @property
    def widget(self) -> tk.Canvas:
        """Access the underlying Tk widget, if needed."""
        return self._c
