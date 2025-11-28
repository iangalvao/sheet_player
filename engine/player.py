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
        score: Score,
        audio: AudioEngine,
        transport: Transport,
        clip: MidiClip,
        update_ui: Callable[[int, list], None],
    ):
        self.score = score
        self.audio = audio
        self.transport = transport
        self.clip = clip
        self.update_ui = update_ui

        self.notes_flat: List[Tuple[int, int, object]] = list(score.all_notes())
        self.is_playing: bool = False
        self.loop_enabled: bool = False
        self.loop_start_index: int = 0
        self.loop_end_index: int = max(0, len(self.notes_flat) - 1)
        self.loop_start_beats = 0.0
        self.loop_end_beats = self._beats_for_index(self.loop_end_index)
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
        if not self.notes_flat or not self.clip.events:
            return

        n = len(self.notes_flat)
        self.loop_start_index = max(0, min(start_idx, n - 1))
        self.loop_end_index = max(self.loop_start_index, min(end_idx, n - 1))

        # --- NEW: compute loop bounds in beats ---
        evs = self.clip.events
        # Guard in case of weird mismatches
        if evs:
            start_idx_clamped = max(0, min(self.loop_start_index, len(evs) - 1))
            end_idx_clamped = max(0, min(self.loop_end_index, len(evs) - 1))

            start_ev = evs[start_idx_clamped]
            end_ev = evs[end_idx_clamped]

            self.loop_start_beats = start_ev.start_beats
            # loop end beat is end-note start + its duration
            self.loop_end_beats = end_ev.start_beats + end_ev.duration_beats
        else:
            self.loop_start_beats = 0.0
            self.loop_end_beats = 0.0

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
        self._start_at_index(start_idx)

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
    
    def _beats_for_index(self, idx: int) -> float:
        """
        Return the absolute beat position for the note at flat index `idx`.
        Example: idx = 0  → 0.0 beats (start of song)
                 idx = 5  → sum of durations of notes 0..4

        Safe for out-of-range: clamps idx into [0, len(notes_flat)-1].
        """
        if not self.notes_flat:
            return 0.0

        # Clamp index
        if idx <= 0:
            return 0.0
        if idx >= len(self.notes_flat):
            idx = len(self.notes_flat) - 1

        total = 0.0
        # accumulate durations of earlier notes
        for i in range(idx):
            _mi, _ni, note = self.notes_flat[i]
            total += note.duration_beats

        return total

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

        events = self.clip.events
        n = len(events)

        # If time went backwards (manual reposition or loop wrap),
        # rescan to find the appropriate event index.
        if current_beats < self._last_processed_beats:
            self._next_event_index = self._find_event_index_for_beats(current_beats)

        # Optional debug, but *only* if index is valid
        if 0 <= self._next_event_index < n:
            ev_debug = events[self._next_event_index]
            print(
                "tick: last=", self._last_processed_beats,
                "current=", current_beats,
                "next_idx=", self._next_event_index,
                "ev_start=", ev_debug.start_beats,
            )
        else:
            print(
                "tick: last=", self._last_processed_beats,
                "current=", current_beats,
                "next_idx=", self._next_event_index,
                "ev_start= <none>",
            )

        # ---- Trigger events whose start is in (last, current] ----
        while self._next_event_index < n:
            ev = events[self._next_event_index]
            start = ev.start_beats

            # Already beyond current beat → nothing else to trigger now
            if start > current_beats:
                break

            # Only trigger if it wasn't already passed on previous tick
            if start > self._last_processed_beats:
                idx = self._next_event_index
                self.update_ui(idx, self.notes_flat)
                duration_s = self._beats_to_seconds(ev.duration_beats)
                self.audio.play_note(ev.pitch, duration_s, volume=0.25)

            self._next_event_index += 1

        # After processing events up to current_beats:
        self._last_processed_beats = current_beats

        # If looping: wrap when transport passes loop_end_beats
        if self.loop_enabled:
            if current_beats >= self.loop_end_beats:
                self._wrap_to_loop_start()
                return

        # If not looping: stop at end of clip
        elif self._next_event_index >= n:
            self.is_playing = False

    def _beats_to_seconds(self, beats: float) -> float:
        beat_duration_s = 60.0 / max(1, self.score.tempo_bpm)
        return beats * beat_duration_s
