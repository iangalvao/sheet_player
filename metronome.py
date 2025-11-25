# metronome.py
import time
from typing import Callable, Optional
from audio_engine import AudioEngine

class Metronome:
    def __init__(self,
                 root,
                 audio: AudioEngine,
                 tempo_bpm: int = 80,
                 beats_per_bar: int = 4,
                 visual_callback: Optional[Callable[[bool], None]] = None):
        self.root = root
        self.audio = audio
        self.tempo_bpm = tempo_bpm
        self.beats_per_bar = beats_per_bar
        self.visual_callback = visual_callback

        self.is_running = False
        self.current_beat = 0  # 1..beats_per_bar
        self.last_beat_time_ms: Optional[int] = None

    def set_tempo(self, bpm: int):
        self.tempo_bpm = max(20, min(bpm, 300))

    def set_beats_per_bar(self, n: int):
        self.beats_per_bar = max(1, n)

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.current_beat = 0
            self._schedule_next()

    def stop(self):
        self.is_running = False

    def _schedule_next(self):
        if not self.is_running:
            return

        self.current_beat = (self.current_beat % self.beats_per_bar) + 1
        strong = (self.current_beat == 1)

        now_ms = int(time.time() * 1000)
        self.last_beat_time_ms = now_ms

        if self.visual_callback:
            self.visual_callback(strong)

        # NEW: non-blocking trigger, mix with note
        self.audio.trigger_click(strong=strong)

        interval_ms = int(60000 / self.tempo_bpm)
        self.root.after(interval_ms, self._schedule_next)

    def get_last_beat_info(self) -> tuple[int, Optional[int]]:
        """
        Returns (current_beat, last_beat_time_ms).
        current_beat is 1..beats_per_bar, or 0 if no beat yet.
        last_beat_time_ms is epoch milliseconds, or None if no beat yet.
        """
        return self.current_beat, self.last_beat_time_ms
