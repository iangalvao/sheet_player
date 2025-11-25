# player.py
from typing import Callable
from score import Score
from audio_engine import AudioEngine

class PlaybackController:
    def __init__(self,
                 root,
                 score: Score,
                 audio: AudioEngine,
                 update_ui: Callable[[int, list], None]):
        self.root = root
        self.score = score
        self.audio = audio
        self.update_ui = update_ui
        self.is_playing = False
        self.current_index = 0
        self.notes_flat = list(score.all_notes())

    def beats_to_seconds(self, beats: float) -> float:
        beat_duration_s = 60.0 / self.score.tempo_bpm
        return beats * beat_duration_s

    def play(self):
        if not self.is_playing:
            self.is_playing = True
            self.current_index = 0
            self.schedule_next()

    def pause(self):
        self.is_playing = False

    def stop(self):
        self.is_playing = False
        self.current_index = 0
        self.update_ui(self.current_index, self.notes_flat)

    def schedule_next(self):
        if not self.is_playing or self.current_index >= len(self.notes_flat):
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
