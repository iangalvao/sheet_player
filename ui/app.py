# app.py
from __future__ import annotations

import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import TYPE_CHECKING, Callable

from domain.score import Score
from engine.audio_engine import AudioEngine
from engine.player import PlaybackController
from engine.metronome import Metronome
from ui.widgets import Widgets
from domain.editor import EditorController
from engine.timebase import beat_label_from_zero_based, compute_next_bar_start_time_ms
from engine.project import Project, Track, TrackType, MidiClip
from engine.transport import Transport, Scheduler
from engine.io import load_project_or_score, save_project_to_json  # or adjust path



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
        self.project: Project | None = None
        self.main_track: Track | None = None
        self.main_clip = None  # type: MidiClip | None
                # After self.score and self.project are ready:
        self.transport = Transport(
            tempo_bpm=self.score.tempo_bpm,
            time_signature=self.score.time_signature,
        )
        self.scheduler = Scheduler(self.transport)
        # Keep the transport clock running; we use it as a global musical timeline.

        self.audio = AudioEngine()
        self.player: PlaybackController | None = None
        self.metronome: Metronome | None = None
        self.editor = EditorController(self.score)


        # Build project based on initial score
        self._build_project_from_score()


        # Editor state
        self.selected_index: int = 0
        self.loop_start_index: int = 0
        self.loop_end_index: int = 0
        self.on_toggle_stick_to_bar = False
        # UI
        self.widgets: WidgetsType = Widgets(self.root, self)

        # Engines (metronome + player)
        self._init_engines()
        self.transport.play()

        # Key bindings
        self.root.bind_all("<Key>", self.on_key)
        # Initial UI sync
        self._start_transport_loop()
        self.update_ui(0)

    # ====== Setup helpers ======================================

    def _apply_loaded_score_and_project(self,
                                        score: Score,
                                        project: Project | None) -> None:
        """
        Central place to update app state after loading either:
        - a legacy Score-only file, or
        - a full Project+Score file.
        """
        # If no project provided, wrap score into a simple one-track project
        if project is None:
            project = Project.from_score(score, track_name=score.title or "Flute")

        self.project = project
        self.score = score

        # Rebuild project/from score (main_clip etc.)
        self._build_project_from_score(self.score)

        # Editor + widgets
        self.editor.set_score(self.score)
        self.widgets.set_score(self.editor.score)
        self.widgets.tempo_var.set(str(self.score.tempo_bpm))

        # Transport/Metronome
        if self.transport is not None:
            self.transport.set_tempo(self.score.tempo_bpm)
            self.transport.set_time_signature(self.score.time_signature)
            self.transport.set_position_beats(0.0)

        if self.metronome is not None:
            self.metronome.set_tempo(self.score.tempo_bpm)
            self.metronome.set_beats_per_bar(self.score.time_signature[0])

        # Player
        if self.player is not None:
            self.player.reset_score(self.score, self.main_clip)
            self.player.notes_flat = self.editor.get_flat_notes()

            # Default loop: whole song
            if self.player.notes_flat:
                self.loop_start_index = 0
                self.loop_end_index = len(self.player.notes_flat) - 1
                self.player.set_loop_region(self.loop_start_index,
                                            self.loop_end_index)

        # UI selection & repaint
        self.editor.set_selection_index(0)
        self.selected_index = 0
        self.update_ui(0)

    def _build_project_from_score(self) -> None:
        """
        Build a Project with a single MIDI track and a single MidiClip
        derived from self.score.

        For now this is purely "engine-side": the UI and playback still
        use Score as before. Later, playback/transport will read from
        Project/Track/Clip.
        """
        track_name = getattr(self.score, "title", "") or "Track 1"

        # Wrap current score into a one-track, one-clip Project
        self.project = Project.from_score(self.score, track_name=track_name)

        # Cache main_track / main_clip for convenience
        if self.project.tracks:
            self.main_track = self.project.tracks[0]
            if self.main_track.clips:
                self.main_clip = self.main_track.clips[0]
            else:
                self.main_clip = None
        else:
            self.main_track = None
            self.main_clip = None

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

        # Player (beat-based)
        self.player = PlaybackController(
            self.root,
            self.score,
            self.audio,
            self.transport,
            self.main_clip,  # created in _build_project_from_score()
            self._player_update_callback,
        )

        # Default loop: whole song
        if self.player.notes_flat:
            self.loop_start_index = 0
            self.loop_end_index = len(self.player.notes_flat) - 1
            self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

        # Staff initial score
        self.widgets.set_score(self.editor.score)


    # ====== Pitch and Beat helpers (diatonic, clamped) ==================

    def _beat_to_fraction_str(self, beat_zero_based: float) -> str:
       return beat_label_from_zero_based(beat_zero_based)

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
        self.editor.set_selection_index(current_idx)
        self.update_ui(current_idx)
    
    def _update_status_from_index(self, idx: int) -> None:
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_status("No notes in score")
            return

        mode = self.editor.get_selection_mode()
        # If we're in interval mode, use the stored interval
        if mode == "interval":
            interval = self.editor.get_selection_interval()
            if interval is not None:
                mi, beat_start, beat_end = interval
                beat_start_str = self._beat_to_fraction_str(beat_start)
                beat_end_str = self._beat_to_fraction_str(beat_end)

                # Overlay
                self.widgets.set_selection_region(mi, beat_start, beat_end)

                # Count how many notes are inside
                selected_indices = self.editor.get_selected_note_indices()
                count = len(selected_indices)
                self.widgets.set_status(
                    f"Interval: measure {mi + 1}, beats {beat_start_str} → {beat_end_str}, {count} note(s)"
                )
                return
            # fall through to note mode if interval is None

        # Default: note mode (or fallback)
        note_info = self.editor.get_note_beat_range_from_flat_index(idx)
        if note_info is None:
            self.widgets.set_status("No notes in score")
            return

        mi, ni, beat_start, beat_end = note_info
        beat_start_str = self._beat_to_fraction_str(beat_start)
        beat_end_str = self._beat_to_fraction_str(beat_end)

        # Overlay uses the single-note interval
        self.widgets.set_selection_region(mi, beat_start, beat_end)

        # Get the actual Note object for the pitch
        _mi_flat, _ni_flat, note = self.player.notes_flat[idx]
        self.widgets.set_status(
            f"Measure {mi + 1}, note {ni + 1}, beats {beat_start_str} → {beat_end_str}, pitch {note.pitch}"
        )


    def update_ui(self, current_idx: int | None = None) -> None:
        """Refresh text label, staff highlight, status bar."""
        if self.player is None or not self.player.notes_flat:
            self.widgets.set_note_list("No notes")
            self.widgets.highlight_note(-1)
            self.widgets.set_status("No notes in score")
            return

        # Sync selection with editor if an explicit index came from playback
        if current_idx is not None:
            self.editor.set_selection_index(current_idx)

        idx = self.editor.get_selection_index()
        if idx is None:
            self.widgets.set_note_list("No notes")
            self.widgets.highlight_note(-1)
            self.widgets.set_status("No notes in score")
            return        

        parts: list[str] = []
        for i, (_, _, note) in enumerate(self.player.notes_flat):
            parts.append(f"[{note.pitch}]" if i == idx else note.pitch)
        self.widgets.set_note_list(" ".join(parts))
        self.widgets.highlight_note(idx)
        self._update_status_from_index(idx)

    # ====== Menu / file actions ================================
    def on_open_project(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            project, score = load_project_or_score(path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load file:\n{e}")
            return

        self._apply_loaded_score_and_project(score, project)
    
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

        # No project in this case → None
        self._apply_loaded_score_and_project(new_score, project=None)

    def on_save_project_as(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return

        try:
            # Ensure project reflects current score
            self.project = Project.from_score(self.score, track_name="Flute")
            save_project_to_json(path, self.project, self.score)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save project:\n{e}")

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
        try:
            bpm = int(raw_value)
        except ValueError:
            return

        bpm = max(20, min(bpm, 300))
        self.score.tempo_bpm = bpm

        if self.metronome is not None:
            self.metronome.set_tempo(bpm)
        if self.transport is not None:
            self.transport.set_tempo(bpm)

    # ====== Transport controls =================================
   
    def _start_transport_loop(self) -> None:
        """
        Start a periodic Tk timer that advances the Transport
        and processes scheduled events.
        """
        import time  # you probably already import time at top; if so, skip this

        self._last_transport_time = time.perf_counter()
        self._transport_tick()
        
        
    def _transport_tick(self) -> None:
        import time

        now = time.perf_counter()
        last = getattr(self, "_last_transport_time", now)
        dt = now - last
        self._last_transport_time = now

        if self.transport is not None:
            self.transport.tick(dt)
        if self.scheduler is not None:
            self.scheduler.process()

        # NEW: playback reacts to the transport clock
        if self.player is not None:
            self.player.process_tick()

        self.root.after(20, self._transport_tick)

   
    def select_interval_for_current_note(self) -> None:
        """
        Use the currently selected note as an interval selection
        (its beat range in its measure).
        """
        idx = self.editor.get_selection_index()
        if idx is None:
            print ("Nothing selected")
            return
        else:
            print("Selected:", idx)
        interval = self.editor.select_interval_for_index(idx)
        if interval is None:
            return

        # UI update: highlight still uses the primary note index
        self.update_ui()

    def clear_interval_selection(self) -> None:
        """
        Return to note-selection mode (keep current selected note).
        """
        self.editor.clear_interval_selection()
        self.update_ui()

   
    def on_start(self) -> None:
        if self.player is None:
            return

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(self.player.play_from_beginning)
        else:
            self.player.play_from_beginning()

    def on_play_from_selected(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return

        def _do():
            self.player.play_from_index(self.editor.get_selection_index())

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(_do)
        else:
            _do()

    def on_pause(self) -> None:
        if self.player is not None:
            self.player.pause()

    def on_stop(self) -> None:
        if self.player is not None:
            self.player.stop()
        self.editor.set_selection_index(0)
        self.update_ui(0)

    def set_loop_in_at_selection(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_start_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_end_index = self.loop_start_index
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_out_at_selection(self) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_end_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_start_index = self.loop_end_index
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)
  
    def on_toggle_loop(self) -> None:
        if self.player is None:
            return
        enabled = self.widgets.loop_var.get()
        self.player.set_loop_enabled(enabled)


    def _stick_to_next_bar_enabled(self) -> bool:
        # Safe guard in case widgets aren't fully initialized
        return bool(getattr(self.widgets, "stick_to_bar_var", None) and self.widgets.stick_to_bar_var.get())

    def _schedule_on_next_bar(self, callback: Callable[[], None]) -> None:
        """
        Call `callback` aligned so that it starts exactly on beat 1
        of the next bar, aligned to the *metronome* clicks.

        If 'stick to next bar' is disabled, or if the metronome is off /
        unavailable, call immediately.
        """
        # If stick-to-next-bar is off, just run now
        if not self._stick_to_next_bar_enabled():
            callback()
            return

        # Need a running metronome to align to its clock
        if self.metronome is None or not self.metronome.is_running:
            callback()
            return

        beats_per_bar = self.score.time_signature[0]
        if beats_per_bar <= 0:
            callback()
            return

        current_beat, last_beat_time_ms = self.metronome.get_last_beat_info()
        now_ms = int(time.time() * 1000)

        target_time_ms = compute_next_bar_start_time_ms(
            tempo_bpm=self.score.tempo_bpm,
            beats_per_bar=beats_per_bar,
            current_beat_in_bar=current_beat,
            last_beat_time_ms=last_beat_time_ms,
            now_ms=now_ms,
        )

        delay_ms = max(0, target_time_ms - now_ms)
        self.root.after(delay_ms, callback)

    # ====== Editing (selection + pitch) ========================

    def move_selection(self, delta: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return
        new_idx = self.editor.move_selection(delta)
        if new_idx is not None:
            self.update_ui(new_idx)

    def change_selected_pitch(self, delta_steps: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return

        # Ask editor to mutate the score and rebuild its flat notes
        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=self.transpose_pitch_diatonic,
        )

        if new_idx is None:
            return

        # Keep player + view in sync with the edited score
        self.widgets.set_score(self.score)
        self.player.notes_flat = self.editor.get_flat_notes()

        self.update_ui(new_idx)

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
        elif key in ("m", "M"):
            # Turn current note into an interval selection
            self.select_interval_for_current_note()
        elif key in ("n", "N"):
            # Back to note-selection mode
            self.clear_interval_selection()

    # ====== Main loop ==========================================

    def run(self) -> None:
        self.root.mainloop()
