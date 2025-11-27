# engine/session.py
from __future__ import annotations

from typing import Optional

from domain.score import Score
from domain.editor import EditorController
from engine.player import PlaybackController
from domain.theory import transpose_pitch_diatonic


class Session:
    """
    Engine-level facade for editing + playback state.

    This class is intentionally UI-agnostic: it does not know about Tk or widgets.
    The UI (App) should:
      - Call these high-level methods (play, stop, move_selection, transpose, etc.)
      - React to selection changes and redraw the UI as needed.
    """

    def __init__(
        self,
        score: Score,
        editor: EditorController,
        player: Optional[PlaybackController] = None,
    ) -> None:
        self.score = score
        self.editor = editor
        self.player: Optional[PlaybackController] = player

        # Loop region in terms of flat-note indices
        self.loop_start_index: int = 0
        self.loop_end_index: int = 0

    # --- wiring -------------------------------------------------

    def attach_player(self, player: PlaybackController) -> None:
        """
        Attach or replace the PlaybackController used by this session.
        """
        self.player = player

    def has_notes(self) -> bool:
        """Convenience guard: player exists and has a non-empty note list."""
        return self.player is not None and bool(self.player.notes_flat)

    # --- loop management ----------------------------------------

    def initialize_loop_region(self) -> None:
        """
        Default loop: the whole song (all notes) if any.
        """
        if self.player is None or not self.player.notes_flat:
            return

        self.loop_start_index = 0
        self.loop_end_index = len(self.player.notes_flat) - 1
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_in_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_start_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_end_index = self.loop_start_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_out_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_end_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_start_index = self.loop_end_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_enabled(self, enabled: bool) -> None:
        if self.player is None:
            return
        self.player.set_loop_enabled(enabled)

    # --- playback controls --------------------------------------

    def play_from_beginning(self) -> None:
        if self.player is None:
            return
        self.player.play_from_beginning()

    def play_from_selection(self) -> None:
        if not self.has_notes():
            return

        idx = self.editor.get_selection_index()
        if idx is None:
            return

        assert self.player is not None
        self.player.play_from_index(idx)

    def pause(self) -> None:
        if self.player is None:
            return
        self.player.pause()

    def stop(self) -> None:
        if self.player is None:
            return
        self.player.stop()
        # Reset selection to the first note (if any)
        self.editor.set_selection_index(0)

    # --- selection / editing ------------------------------------

    def move_selection(self, delta: int) -> Optional[int]:
        """
        Move note selection by +1 / -1, etc.
        Returns the new index or None if it did not change.
        """
        if not self.has_notes():
            return None

        new_idx = self.editor.move_selection(delta)
        return new_idx

    def transpose_selected(self, delta_steps: int) -> Optional[int]:
        """
        Transpose the currently selected note diatonically.
        Returns the new selected index, or None if nothing changed.

        This mutates the underlying Score via EditorController.
        """
        if not self.has_notes():
            return None

        # Assumes EditorController.transpose_selected(delta, transpose_pitch_func=...)
        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=transpose_pitch_diatonic,
        )
        return new_idx

    # --- interval selection -------------------------------------

    def select_interval_for_current_note(self) -> bool:
        """
        Use the currently selected note as an interval selection.

        Returns True if an interval was selected, False otherwise.
        """
        idx = self.editor.get_selection_index()
        if idx is None:
            return False

        interval = self.editor.select_interval_for_index(idx)
        return interval is not None

    def clear_interval_selection(self) -> None:
        self.editor.clear_interval_selection()
