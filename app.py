# app.py
from __future__ import annotations

import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING

from score import Score
from audio_engine import AudioEngine
from player import PlaybackController
from metronome import Metronome
from widgets import Widgets

if TYPE_CHECKING:
    # for type checkers only; avoids circular import at runtime
    from widgets import Widgets as WidgetsType


def load_score_from_json(path: str) -> Score:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Score.from_dict(data)


def save_score_to_json(score: Score, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score.to_dict(), f, indent=2)


class App:
    LETTER_ORDER = ["C", "D", "E", "F", "G", "A", "B"]
    MIN_DIATONIC_INDEX = LETTER_ORDER.index("E") + 7 * 4  # E4
    MAX_DIATONIC_INDEX = LETTER_ORDER.index("F") + 7 * 5  # F5

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Flute Practice Prototype")

        # Core state
        self.score: Score = self._make_demo_score()
        self.audio = AudioEngine()
        self.player: PlaybackController | None = None
        self.metronome: Metronome | None = None

        # Editor state
        self.selected_index: int = 0
        self.loop_start_index: int = 0
        self.loop_end_index: int = 0
        
        # UI
        self.widgets: WidgetsType = Widgets(self.root, self)

        # Engines (metronome + player)
        self._init_engines()

        # Key bindings
        self.root.bind_all("<Key>", self.on_key)

        # Initial UI sync
        self.update_ui(0)

    # ====== Setup helpers ======================================

    def _make_demo_score(self) -> Score:
        data = {
            "title": "Simple Flute Tune",
            "tempo_bpm": 80,
            "time_signature": [4, 4],
            "measures": [
                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 1.0},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 1.0},
                        {"pitch": "E5", "duration_beats": 1.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 1.0},
                        {"pitch": "E5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 1.0},
                        {"pitch": "C5", "duration_beats": 1.0},
                    ]
                },
            ],
        }
        return Score.from_dict(data)

    
    def _init_engines(self) -> None:
        # Metronome
        beats_per_bar = self.score.time_signature[0]
        self.metronome = Metronome(
            self.root,
            self.audio,
            tempo_bpm=self.score.tempo_bpm,
            beats_per_bar=beats_per_bar,
            visual_callback=self.widgets.metro_visual,
        )
        # Player
        self.player = PlaybackController(
            self.root,
            self.score,
            self.audio,
            self._player_update_callback,
        )
        self.player.reset_score(self.score)

        # Default loop: whole song
        if self.player.notes_flat:
            self.loop_start_index = 0
            self.loop_end_index = len(self.player.notes_flat) - 1
            self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

        # Staff initial score
        self.widgets.set_score(self.score)


    # ====== Pitch helpers (diatonic, clamped) ==================

    def pitch_to_diatonic_index(self, pitch: str) -> int:
        up = pitch.upper()
        if up == "REST":
            return self.MIN_DIATONIC_INDEX

        i = 0
        while i < len(pitch) and not pitch[i].isdigit():
            i += 1
        name = pitch[:i]
        octave_str = pitch[i:] or "4"

        letter = name[0].upper()
        octave = int(octave_str)

        if letter not in self.LETTER_ORDER:
            return self.MIN_DIATONIC_INDEX

        return self.LETTER_ORDER.index(letter) + 7 * octave

    def diatonic_index_to_pitch(self, index: int) -> str:
        octave, letter_idx = divmod(index, 7)
        letter = self.LETTER_ORDER[letter_idx]
        return f"{letter}{octave}"

    def transpose_pitch_diatonic(self, pitch: str, steps: int) -> str:
        up = pitch.upper()
        if up == "REST":
            return pitch

        idx = self.pitch_to_diatonic_index(pitch)
        idx_new = idx + steps

        if idx_new < self.MIN_DIATONIC_INDEX:
            idx_new = self.MIN_DIATONIC_INDEX
        if idx_new > self.MAX_DIATONIC_INDEX:
            idx_new = self.MAX_DIATONIC_INDEX

        return self.diatonic_index_to_pitch(idx_new)

    # ====== UI update glue =====================================

    def _player_update_callback(self, current_idx, _notes_flat) -> None:
        """Called by PlaybackController when playback advances."""
        self.selected_index = current_idx
        self.update_ui(current_idx)

    def _update_status_from_index(self, idx: int) -> None:
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_status("No notes in score")
            return

        mi, ni, note = self.player.notes_flat[idx]
        measure = self.score.measures[mi]

        beat_pos = 0.0
        for j, n in enumerate(measure.notes):
            if j == ni:
                break
            beat_pos += n.duration_beats

        center_beat = beat_pos + measure.notes[ni].duration_beats / 2.0
        self.widgets.set_status(
            f"Measure {mi + 1}, note {ni + 1}, beat ~{center_beat:.2f}, "
            f"pitch {note.pitch}"
        )

    def update_ui(self, current_idx: int | None = None) -> None:
        """Refresh text label, staff highlight, status bar."""
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_note_list("No notes")
            self.widgets.highlight_note(-1)
            self.widgets.set_status("No notes in score")
            return

        idx = self.selected_index if current_idx is None else current_idx
        idx = max(0, min(len(self.player.notes_flat) - 1, idx))
        self.selected_index = idx

        parts: list[str] = []
        for i, (_, _, note) in enumerate(self.player.notes_flat):
            parts.append(f"[{note.pitch}]" if i == idx else note.pitch)
        self.widgets.set_note_list(" ".join(parts))
        self.widgets.highlight_note(idx)
        self._update_status_from_index(idx)

    # ====== Menu / file actions ================================
    
    def on_open(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            new_score = load_score_from_json(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load score:\n{e}")
            return

        self.score = new_score
        self.widgets.set_score(self.score)
        self.widgets.tempo_var.set(str(self.score.tempo_bpm))

        # Reuse existing player if present, otherwise create new
        if self.player is None:
            self.player = PlaybackController(
                self.root,
                self.score,
                self.audio,
                self._player_update_callback,
            )

        self.player.reset_score(self.score)
        self.selected_index = 0

        # Reset loop to full song for new score
        if self.player.notes_flat:
            self.loop_start_index = 0
            self.loop_end_index = len(self.player.notes_flat) - 1
            self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

        self.update_ui(0)


    def on_save_as(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            save_score_to_json(self.score, path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save score:\n{e}")

    def on_quit(self) -> None:
        self.root.quit()

    # ====== Metronome / tempo ==================================

    def on_toggle_metronome(self) -> None:
        if self.metronome is None:
            return
        if self.widgets.metro_on_var.get():
            self.metronome.set_tempo(self.score.tempo_bpm)
            self.metronome.set_beats_per_bar(self.score.time_signature[0])
            self.metronome.start()
        else:
            self.metronome.stop()

    def on_tempo_change(self, raw_value: str) -> None:
        if self.metronome is None:
            return
        try:
            bpm = int(raw_value)
            bpm = max(20, min(bpm, 300))
            self.score.tempo_bpm = bpm
            self.metronome.set_tempo(bpm)
        except ValueError:
            # ignore invalid input
            pass

    # ====== Transport controls =================================
   
    def on_start(self) -> None:
        if self.player is not None:
            self.player.play_from_beginning()

    def on_start_next_bar(self) -> None:
        if self.metronome is None or self.player is None:
            return

        if self.widgets.metro_on_var.get() and self.metronome.is_running:
            beat_interval_ms = int(60000 / self.score.tempo_bpm)
            current_beat, last_beat_time_ms = self.metronome.get_last_beat_info()
            bpb = self.metronome.beats_per_bar

            if current_beat == 0 or last_beat_time_ms is None:
                beats_remaining = bpb
                now_ms = int(time.time() * 1000)
                target_time_ms = now_ms + beats_remaining * beat_interval_ms
            else:
                beats_remaining = (bpb - current_beat + 1)
                target_time_ms = last_beat_time_ms + beats_remaining * beat_interval_ms

            now_ms = int(time.time() * 1000)
            delay_ms = max(0, target_time_ms - now_ms)
            self.root.after(delay_ms, self.player.play_from_beginning)
        else:
            self.player.play_from_beginning()
            
    def on_play_from_selected(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        self.player.play_from_index(self.selected_index)

    def on_pause(self) -> None:
        if self.player is not None:
            self.player.pause()

    def on_stop(self) -> None:
        if self.player is not None:
            self.player.stop()
        self.selected_index = 0
        self.update_ui(0)

    def set_loop_in_at_selection(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        self.loop_start_index = self.selected_index
        if self.loop_end_index < self.loop_start_index:
            self.loop_end_index = self.loop_start_index
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_out_at_selection(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        self.loop_end_index = self.selected_index
        if self.loop_end_index < self.loop_start_index:
            self.loop_start_index = self.loop_end_index
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def on_toggle_loop(self) -> None:
        if self.player is None:
            return
        enabled = self.widgets.loop_var.get()
        self.player.set_loop_enabled(enabled)


    # ====== Editing (selection + pitch) ========================

    def move_selection(self, delta: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        new_idx = max(0, min(len(self.player.notes_flat) - 1, self.selected_index + delta))
        self.selected_index = new_idx
        self.update_ui(new_idx)

    def change_selected_pitch(self, delta_steps: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        idx = self.selected_index
        mi, ni, note = self.player.notes_flat[idx]
        old_pitch = note.pitch
        new_pitch = self.transpose_pitch_diatonic(old_pitch, delta_steps)
        note.pitch = new_pitch

        # After editing, re-sync staff + flat list
        self.widgets.set_score(self.score)
        self.player.notes_flat = list(self.score.all_notes())
        if idx >= len(self.player.notes_flat):
            idx = len(self.player.notes_flat) - 1
        self.selected_index = idx
        self.update_ui(idx)
        
    def on_key(self, event) -> None:
        key = event.keysym

        if key in ("a", "A"):
            self.move_selection(-1)
        elif key in ("d", "D"):
            self.move_selection(1)
        elif key == "Up":
            self.change_selected_pitch(+1)
        elif key == "Down":
            self.change_selected_pitch(-1)
        elif key in ("i", "I"):
            self.set_loop_in_at_selection()
        elif key in ("o", "O"):
            self.set_loop_out_at_selection()

    # ====== Main loop ==========================================

    def run(self) -> None:
        self.root.mainloop()
