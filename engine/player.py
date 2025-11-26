# player.py
from __future__ import annotations

from typing import Callable, Optional, List, Tuple

from domain.score import Score
from engine.project import MidiClip
from engine.audio_engine import AudioEngine
from engine.transport import Transport


class PlaybackController:
    """
    Beat-based playback controller.

    - Reads events from a MidiClip.
    - Uses Transport.current_beats as the master musical clock.
    - Triggers AudioEngine.play_note for events whose start_beats are reached.
    - Keeps a flat note list for UI highlighting, 1:1 with events.
    """

    def __init__(
        self,
        root,
        score: Score,
        audio: AudioEngine,
        transport: Transport,
        clip: MidiClip,
        update_ui: Callable[[int, list], None],
    ) -> None:
        self.root = root
        self.score = score
        self.audio = audio
        self.transport = transport
        self.clip = clip
        self.update_ui = update_ui

        # Flat (measure_index, note_index, Note) list for UI
        self.notes_flat: List[Tuple[int, int, object]] = list(score.all_notes())

        # Playback state
        self.is_playing: bool = False

        # Loop in terms of indices (for now)
        self.loop_enabled: bool = False
        self.loop_start_index: int = 0
        self.loop_end_index: int = max(0, len(self.notes_flat) - 1)

        # Internal event pointer & time tracking
        self._next_event_index: int = 0
        self._last_processed_beats: Optional[float] = None

    # ------------------------------------------------------------------
    # Score / clip reset
    # ------------------------------------------------------------------
    def reset_score(self, score: Score, clip: MidiClip) -> None:
        """
        Called when we load a new score.

        Keeps interface compatible for the rest of the app.
        """
        self.score = score
        self.clip = clip
        self.notes_flat = list(score.all_notes())

        self.loop_start_index = 0
        self.loop_end_index = max(0, len(self.notes_flat) - 1)

        self.is_playing = False
        self._next_event_index = 0
        self._last_processed_beats = None

    # ------------------------------------------------------------------
    # Loop controls (still index-based)
    # ------------------------------------------------------------------
    def set_loop_region(self, start_idx: int, end_idx: int) -> None:
        if not self.notes_flat:
            self.loop_enabled = False
            return

        start_idx = max(0, min(start_idx, len(self.notes_flat) - 1))
        end_idx = max(0, min(end_idx, len(self.notes_flat) - 1))
        if end_idx < start_idx:
            start_idx, end_idx = end_idx, start_idx

        self.loop_start_index = start_idx
        self.loop_end_index = end_idx

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_enabled = enabled

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _find_event_index_for_beats(self, beats: float) -> int:
        """
        Find the first event whose start_beats >= beats.
        """
        events = self.clip.events
        i = 0
        n = len(events)
        while i < n and events[i].start_beats < beats:
            i += 1
        return i

    def _wrap_to_loop_start(self) -> None:
        """
        Wrap playback to the loop start index and reposition transport.
        """
        if not self.clip.events or not self.notes_flat:
            return

        start_idx = max(0, min(self.loop_start_index, len(self.clip.events) - 1))
        self._next_event_index = start_idx

        start_beat = self.clip.events[start_idx].start_beats
        self.transport.set_position_beats(start_beat)
        self._last_processed_beats = None  # force a clean boundary

    # ------------------------------------------------------------------
    # Play / pause / stop
    # ------------------------------------------------------------------
    def play_from_beginning(self) -> None:
        """Start from beginning (or loop start if loop_enabled)."""
        if not self.notes_flat or not self.clip.events:
            return

        if self.loop_enabled:
            idx = self.loop_start_index
        else:
            idx = 0

        self._start_at_index(idx)

    def play_from_index(self, index: int | None) -> None:
        if index is None or not self.clip.events:
            return
        idx = max(0, min(index, len(self.clip.events) - 1))
        self._start_at_index(idx)

    def _start_at_index(self, index: int) -> None:
        """
        Internal: set transport position & event pointer, then start playback.
        """
        if not self.clip.events:
            return

        index = max(0, min(index, len(self.clip.events) - 1))
        self._next_event_index = index

        start_beat = self.clip.events[index].start_beats
        self.transport.set_position_beats(start_beat)

        # IMPORTANT: initialize last_processed just *before* start_beat,
        # so the first tick will see the note in (last, current].
        self._last_processed_beats = start_beat - 1e-6

        self.transport.play()
        self.is_playing = True


    def play(self) -> None:
        """
        Backwards-compatible: same as play_from_beginning().
        """
        self.play_from_beginning()

    def pause(self) -> None:
        self.is_playing = False
        # We *don't* stop the transport; it's a global clock used by other stuff.
        # If later you want "hard pause", we can introduce a separate playhead concept.

    def stop(self) -> None:
        self.is_playing = False
        self._next_event_index = 0
        self._last_processed_beats = None
        if self.notes_flat:
            self.update_ui(0, self.notes_flat)

    # ------------------------------------------------------------------
    # Beat-based processing (called from App's transport loop)
    # ------------------------------------------------------------------
    def process_tick(self) -> None:
        """
        Called regularly from App._transport_tick().
        Looks at transport.current_beats and triggers all events
        that start between last_processed_beats and current_beats.
        """
        if not self.is_playing:
            return
        if not self.clip.events or not self.notes_flat:
            return

        current_beats = self.transport.current_beats

        # Initialize last_processed_beats on first run
        if self._last_processed_beats is None:
            self._last_processed_beats = current_beats

        # If time went backwards (manual reposition or loop wrap),
        # rescan to find the appropriate event index.
        if current_beats < self._last_processed_beats:
            self._next_event_index = self._find_event_index_for_beats(current_beats)

        events = self.clip.events
        n = len(events)

        # Trigger events whose start is in (last, current]
        while self._next_event_index < n:
            ev = events[self._next_event_index]
            start = ev.start_beats

            # Already beyond current beat → nothing else to trigger now
            if start > current_beats:
                break

            # Only trigger if it wasn't already passed on previous tick
            if start > self._last_processed_beats:
                idx = self._next_event_index

                # UI highlight (assumes MidiClip order == notes_flat order)
                self.update_ui(idx, self.notes_flat)

                # Convert beats duration to seconds using score tempo
                duration_s = self._beats_to_seconds(ev.duration_beats)
                self.audio.play_note(ev.pitch, duration_s, volume=0.25)

            self._next_event_index += 1

            # Handle loop wrap based on indices
            if self.loop_enabled and self._next_event_index > self.loop_end_index:
                self._wrap_to_loop_start()
                # After wrapping we break this tick; next process_tick
                # will continue from new position.
                self._last_processed_beats = self.transport.current_beats
                return

        self._last_processed_beats = current_beats

        # If we hit the end and no loop, stop
        if self._next_event_index >= n and not self.loop_enabled:
            self.is_playing = False

    def _beats_to_seconds(self, beats: float) -> float:
        beat_duration_s = 60.0 / max(1, self.score.tempo_bpm)
        return beats * beat_duration_s
