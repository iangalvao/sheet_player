# widgets.py
from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from staff_view import StaffView
from score import Score

if TYPE_CHECKING:
    from app import App


class Widgets:
    """
    Builds all Tk widgets and binds their commands directly to App methods.
    Exposes a small API for App to update the view.
    """

    def __init__(self, root: tk.Tk, app: "App") -> None:
        self.root = root
        self.app = app

        # === Menu: File ===
        menubar = tk.Menu(root)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Open...", command=self.app.on_open)
        filemenu.add_command(label="Save As...", command=self.app.on_save_as)
        filemenu.add_separator()
        filemenu.add_command(label="Quit", command=self.app.on_quit)
        menubar.add_cascade(label="File", menu=filemenu)
        root.config(menu=menubar)

        # === Staff view + note label ===
        self.staff_view = StaffView(root, width=800, height=160)
        self.staff_view.pack(pady=5)
        self.staff_view.set_score(app.score)

        self.note_label = tk.Label(root, font=("Arial", 24))
        self.note_label.pack(pady=10)

        # === Metronome panel ===
        metro_frame = tk.Frame(root)
        metro_frame.pack(pady=5)

        tk.Label(metro_frame, text="Metronome:").pack(side=tk.LEFT)

        self.metro_canvas = tk.Canvas(metro_frame, width=24, height=24, highlightthickness=0)
        self.metro_canvas.pack(side=tk.LEFT, padx=5)
        self._beat_circle = self.metro_canvas.create_oval(
            4, 4, 20, 20, fill="grey", outline="black"
        )

        self.metro_on_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            metro_frame,
            text="On",
            variable=self.metro_on_var,
            command=self.app.on_toggle_metronome,
        ).pack(side=tk.LEFT)

        # === Tempo control ===
        tempo_frame = tk.Frame(root)
        tempo_frame.pack(pady=5)
        tk.Label(tempo_frame, text="Tempo (bpm):").pack(side=tk.LEFT)

        self.tempo_var = tk.StringVar(value=str(app.score.tempo_bpm))

        def _tempo_changed(*_):
            self.app.on_tempo_change(self.tempo_var.get())

        tempo_entry = tk.Entry(tempo_frame, textvariable=self.tempo_var, width=5)
        tempo_entry.pack(side=tk.LEFT)
        self.tempo_var.trace_add("write", _tempo_changed)

        # === Transport ===
        controls = tk.Frame(root)
        controls.pack(pady=10)

        tk.Button(controls, text="Start", command=self.app.on_start).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(
            controls,
            text="Play from selected",
            command=self.app.on_play_from_selected,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(
            controls,
            text="Start next bar",
            command=self.app.on_start_next_bar,
        ).pack(side=tk.LEFT, padx=5)
        tk.Button(controls, text="Pause", command=self.app.on_pause).pack(
            side=tk.LEFT, padx=5
        )
        tk.Button(controls, text="Stop", command=self.app.on_stop).pack(
            side=tk.LEFT, padx=5
        )

        # Loop toggle
        self.loop_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            controls,
            text="Loop",
            variable=self.loop_var,
            command=self.app.on_toggle_loop,
        ).pack(side=tk.LEFT, padx=10)


        # === Status bar ===
        self.status_var = tk.StringVar(value="Ready")
        status_label = tk.Label(root, textvariable=self.status_var, anchor="w")
        status_label.pack(fill="x", side=tk.BOTTOM, padx=5, pady=3)

    # --------- Small API for App to control the view -----------

    def metro_visual(self, strong: bool) -> None:
        color = "tomato" if strong else "gold"
        self.metro_canvas.itemconfig(self._beat_circle, fill=color)
        self.root.after(
            80, lambda: self.metro_canvas.itemconfig(self._beat_circle, fill="grey")
        )

    def set_score(self, score: Score) -> None:
        self.staff_view.set_score(score)

    def set_note_list(self, text: str) -> None:
        self.note_label.config(text=text)

    def highlight_note(self, index: int) -> None:
        # ScoreView already handles out-of-range gracefully (we used -1 in App)
        self.staff_view.highlight_note(index)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
