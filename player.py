# player.py
from typing import Callable
from score import Score
from audio_engine import AudioEngine


class PlaybackController:
    def __init__(
        self,
        root,
        score: Score,
        audio: AudioEngine,
        update_ui: Callable[[int, list], None],
    ):
        self.root = root
        self.score = score
        self.audio = audio
        self.update_ui = update_ui

        self.is_playing = False
        self.current_index = 0
        self.notes_flat = list(score.all_notes())

        # Loop state
        self.loop_enabled: bool = False
        self.loop_start_index: int = 0
        self.loop_end_index: int = max(0, len(self.notes_flat) - 1)

    # ---- score / loop config ---------------------------------

    def reset_score(self, score: Score) -> None:
        """Replace score and recompute flat notes & loop range."""
        self.score = score
        self.notes_flat = list(score.all_notes())
        self.current_index = 0
        self.loop_start_index = 0
        self.loop_end_index = max(0, len(self.notes_flat) - 1)

    def set_loop_region(self, start_idx: int, end_idx: int) -> None:
        """Set loop range [start_idx, end_idx], clamped and validated."""
        if not self.notes_flat:
            self.loop_start_index = 0
            self.loop_end_index = 0
            return

        n = len(self.notes_flat)
        start = max(0, min(start_idx, n - 1))
        end = max(0, min(end_idx, n - 1))

        if end < start:
            # invalid / empty range -> normalize to single note
            start = end

        self.loop_start_index = start
        self.loop_end_index = end

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_enabled = bool(enabled)

    # ---- timing ----------------------------------------------

    def beats_to_seconds(self, beats: float) -> float:
        beat_duration_s = 60.0 / self.score.tempo_bpm
        return beats * beat_duration_s

    # ---- playback entrypoints --------------------------------

    def play_from_beginning(self) -> None:
        """Start from beginning (or loop start if loop_enabled)."""
        if not self.notes_flat:
            return
        if not self.is_playing:
            self.is_playing = True
            self.current_index = (
                self.loop_start_index if self.loop_enabled else 0
            )
            self.schedule_next()

    def play_from_index(self, index: int) -> None:
        """Start playback from a specific index."""
        if not self.notes_flat:
            return
        idx = max(0, min(len(self.notes_flat) - 1, index))
        self.is_playing = True
        self.current_index = idx
        self.schedule_next()

    # backwards compatibility
    def play(self) -> None:
        self.play_from_beginning()

    def pause(self) -> None:
        self.is_playing = False

    def stop(self) -> None:
        self.is_playing = False
        self.current_index = 0
        self.update_ui(self.current_index, self.notes_flat)

    # ---- core scheduler --------------------------------------

    def schedule_next(self) -> None:
        if not self.is_playing or not self.notes_flat:
            self.is_playing = False
            return

        # Apply loop wrapping if needed
        if self.loop_enabled and self.current_index > self.loop_end_index:
            self.current_index = self.loop_start_index

        # End of score (no loop or invalid loop)
        if self.current_index >= len(self.notes_flat):
            self.is_playing = False
            return

        idx = self.current_index
        mi, ni, note = self.notes_flat[idx]
        self.update_ui(idx, self.notes_flat)

        duration_s = self.beats_to_seconds(note.duration_beats)

        # Ask audio engine to start this note (non-blocking)
        self.audio.play_note(note.pitch, duration_s, volume=0.25)

        self.current_index += 1
        self.root.after(int(duration_s * 1000), self.schedule_next)
