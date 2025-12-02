# ui/canvas_api.py
from __future__ import annotations

from typing import Protocol, Any, Tuple


class CanvasAPI(Protocol):
    """
    Minimal drawing surface abstraction.

    Implemented by backend canvases (Tk, web, etc.).
    """

    # Geometry
    def get_width(self) -> int:
        ...

    def get_height(self) -> int:
        ...

    # State / config
    def config(self, **kwargs: Any) -> None:
        ...

    # Drawing primitives
    def create_line(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        **kwargs: Any,
    ) -> Any:
        ...

    def create_rectangle(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        **kwargs: Any,
    ) -> Any:
        ...

    def create_image(
        self,
        x: float,
        y: float,
        **kwargs: Any,
    ) -> Any:
        ...

    def create_text(
        self,
        x: float,
        y: float,
        **kwargs: Any,
    ) -> Any:
        ...

    # Housekeeping
    def delete(self, what: Any) -> None:
        ...

    # Scrolling
    def xview(self) -> Tuple[float, float]:
        ...

    def xview_moveto(self, fraction: float) -> None:
        ...
