# ui/file_actions.py
from __future__ import annotations

import json
from typing import Callable, Optional

from tkinter import filedialog, messagebox

from domain.score import Score
from engine.project import Project
from engine.io import load_project_or_score, save_project_to_json


def load_score_from_json(path: str) -> Score:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Score.from_dict(data)


def save_score_to_json(score: Score, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score.to_dict(), f, indent=2)


class FileActions:
    """
    Handles open/save dialogs and JSON I/O for Score / Project.

    All application state changes happen via the callbacks that App passes in,
    so this stays decoupled from App internals.
    """

    def __init__(
        self,
        root,
        apply_loaded_score_and_project: Callable[[Score, Optional[Project]], None],
        get_score: Callable[[], Score],
    ) -> None:
        self.root = root
        self._apply_loaded = apply_loaded_score_and_project
        self._get_score = get_score

    # ---- Menu / file actions -----------------------------------------

    def open_project(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            project, score = load_project_or_score(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}", parent=self.root)
            return

        self._apply_loaded(score, project)

    def open_score(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            new_score = load_score_from_json(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load score:\n{e}", parent=self.root)
            return

        # No project in this case → None
        self._apply_loaded(new_score, project=None)

    def save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            score = self._get_score()
            # Wrap current score into a simple one-track project
            track_name = getattr(score, "title", "") or "Flute"
            project = Project.from_score(score, track_name=track_name)
            save_project_to_json(path, project, score)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save project:\n{e}", parent=self.root)

    def save_score_as(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            defaultextension=".json",
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            score = self._get_score()
            save_score_to_json(score, path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save score:\n{e}", parent=self.root)
