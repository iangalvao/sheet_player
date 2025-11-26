# engine/transport.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Tuple


@dataclass
class Transport:
    """
    Central musical clock, in beats.

    For now it's a simple 'always running' clock driven by Tk via App.
    Later it can be tied more tightly to playback and looping.
    """
    tempo_bpm: int
    time_signature: tuple[int, int]

    current_beats: float = 0.0
    playing: bool = True  # we keep it always running for now

    loop_enabled: bool = False
    loop_start: float = 0.0
    loop_end: float = 0.0

    def set_tempo(self, bpm: int) -> None:
        self.tempo_bpm = max(1, bpm)

    def set_time_signature(self, ts: tuple[int, int]) -> None:
        self.time_signature = ts

    def set_position_beats(self, beats: float) -> None:
        self.current_beats = max(0.0, beats)

    def play(self) -> None:
        self.playing = True

    def stop(self) -> None:
        self.playing = False

    def tick(self, dt_seconds: float) -> None:
        """
        Advance the musical time by dt_seconds, according to tempo.
        """
        if not self.playing or self.tempo_bpm <= 0:
            return

        beats_per_second = self.tempo_bpm / 60.0
        self.current_beats += beats_per_second * dt_seconds

        # Optional simple loop support (we'll use more later)
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
    """
    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self._events: List[Tuple[float, Callable[[], None]]] = []

    def schedule_at(self, beat: float, callback: Callable[[], None]) -> None:
        """
        Schedule a callback to run when transport.current_beats >= beat.
        """
        self._events.append((beat, callback))
        # keep events ordered by beat for simpler processing
        self._events.sort(key=lambda e: e[0])

    def clear(self) -> None:
        self._events.clear()

    def process(self) -> None:
        """
        Check current_beats and run any due callbacks.
        Called regularly from App's Tk timer.
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
