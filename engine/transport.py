from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple


@dataclass
class Transport:
    """
    Central musical clock, in beats.

    For now it's a simple 'always running' clock driven by the UI
    (App → Session.process_tick → Transport.tick).

    Responsibilities:
      - Keep track of current position in beats.
      - Advance time according to tempo (BPM).
      - (Optionally) wrap inside a loop range [loop_start, loop_end).

    Note:
      Loop fields are currently not wired to the rest of the engine; the
      main loop semantics live in PlaybackController. These fields give us
      a place to move that logic in the future.
    """

    tempo_bpm: int
    time_signature: tuple[int, int]

    current_beats: float = 0.0
    playing: bool = True  # global clock on/off

    loop_enabled: bool = False
    loop_start: float = 0.0
    loop_end: float = 0.0

    # ---------------- basic control ----------------

    def set_tempo(self, bpm: int) -> None:
        """Set tempo in BPM (clamped to >= 1)."""
        self.tempo_bpm = max(1, int(bpm))

    def set_time_signature(self, ts: tuple[int, int]) -> None:
        """
        Set time signature as (numerator, denominator), e.g., (4, 4) for 4/4.
        """
        self.time_signature = ts

    def set_position_beats(self, beats: float) -> None:
        """Set the current position in beats (>= 0)."""
        self.current_beats = max(0.0, float(beats))

    def play(self) -> None:
        """Turn the global clock on."""
        self.playing = True

    def stop(self) -> None:
        """Turn the global clock off (time no longer advances in tick())."""
        self.playing = False

    # ---------------- derived quantities ----------------

    @property
    def beats_per_second(self) -> float:
        """Tempo as beats per second."""
        return self.tempo_bpm / 60.0 if self.tempo_bpm > 0 else 0.0

    @property
    def seconds_per_beat(self) -> float:
        """Inverse of beats_per_second."""
        return 1.0 / self.beats_per_second if self.beats_per_second > 0 else 0.0

    def get_bar_and_beat(self) -> Tuple[int, float]:
        """
        Return (bar_index, beat_in_bar) based on current_beats and time_signature.

        Example in 4/4:
          current_beats = 0.0 → (0, 0.0)
          current_beats = 4.0 → (1, 0.0)
          current_beats = 5.5 → (1, 1.5)
        """
        beats_per_bar = self.time_signature[0] if self.time_signature else 4
        if beats_per_bar <= 0:
            return 0, self.current_beats

        bar_index = int(self.current_beats // beats_per_bar)
        beat_in_bar = self.current_beats - bar_index * beats_per_bar
        return bar_index, beat_in_bar

    # ---------------- main time update ----------------

    def tick(self, dt_seconds: float) -> None:
        """
        Advance the musical time by dt_seconds, according to tempo.

        Called regularly from Session.process_tick().
        """
        if not self.playing or self.tempo_bpm <= 0:
            return

        self.current_beats += self.beats_per_second * dt_seconds

        # Optional simple loop support (currently not used by PlaybackController).
        if self.loop_enabled and self.loop_end > self.loop_start:
            total = self.loop_end - self.loop_start
            if total > 0 and self.current_beats >= self.loop_end:
                # wrap around within the loop range
                delta = self.current_beats - self.loop_start
                self.current_beats = self.loop_start + (delta % total)


class Scheduler:
    """
    Tiny beat-based scheduler: run callbacks once when transport
    reaches or passes a given beat.

    One-shot: events are removed after they fire.
    """

    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._events: List[Tuple[float, Callable[[], None]]] = []

    def schedule_at(self, beat: float, callback: Callable[[], None]) -> None:
        """
        Schedule a callback to run when transport.current_beats >= beat.
        """
        self._events.append((float(beat), callback))
        # keep events ordered by beat for simpler processing
        self._events.sort(key=lambda e: e[0])

    def clear(self) -> None:
        """Remove all scheduled callbacks."""
        self._events.clear()

    def process(self) -> None:
        """
        Check current_beats and run any due callbacks.
        Called regularly from Session.process_tick().
        """
        if not self._events:
            return

        now_beats = self.transport.current_beats
        to_run: List[Tuple[float, Callable[[], None]]] = []
        remaining: List[Tuple[float, Callable[[], None]]] = []

        for beat, cb in self._events:
            if beat <= now_beats:
                to_run.append((beat, cb))
            else:
                remaining.append((beat, cb))

        self._events = remaining

        for _beat, cb in to_run:
            cb()
