# app.py
from __future__ import annotations

import time
import tkinter as tk
from typing import TYPE_CHECKING, Callable

from engine.audio_engine import AudioEngine
from engine.player import PlaybackController
from engine.metronome import Metronome
from engine.timebase import beat_label_from_zero_based
from engine.project import Project, Track
from engine.transport import Transport, Scheduler
from engine.session import Session
from ui.widgets import Widgets
from ui.file_actions import FileActions
from domain.editor import EditorController
from domain.score import Score
from domain.theory import transpose_pitch_diatonic

if TYPE_CHECKING:
    # for type checkers only; avoids circular import at runtime
    from widgets import Widgets as WidgetsType



class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Flute Practice Prototype")

                # Core state
        self.score: Score = self._make_demo_score()
        self.project: Project | None = None
        self.main_track: Track | None = None
        self.main_clip = None

        # Core engine objects
        self.transport = Transport(
            tempo_bpm=self.score.tempo_bpm,
            time_signature=self.score.time_signature,
        )
        self.scheduler = Scheduler(self.transport)
        self.audio = AudioEngine()
        self.player: PlaybackController | None = None
        self.metronome: Metronome | None = None

        self.editor = EditorController(self.score)


        # Build project based on initial score

        # Engine facade: now knows about transport/scheduler
        self.session = Session(
            score=self.score,
            editor=self.editor,
            transport=self.transport,
            scheduler=self.scheduler,
        )
        
        # File / project actions helper
        self.file_actions = FileActions(
            root=self.root,
            apply_loaded_score_and_project=self._apply_loaded_score_and_project,
            get_score=lambda: self.score,
        )

        # Inform session about the project
        self._build_project_from_score()
        self.session.set_project(self.project)

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

        # Sync the session with the loaded project
        self.session.set_project(self.project)
        # Editor + widgets
        
        self.editor.set_score(self.score)
        self.session.score = self.score
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

            # Re-attach to session & reset loop
            self.session.score = self.score
            self.session.attach_player(self.player)
            self.session.initialize_loop_region()
        # UI selection & repaint
        self.editor.set_selection_index(0)
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
            
        # NEW: inform session (if it already exists)
        if hasattr(self, "session"):
            self.session.set_project(self.project)

    def _make_demo_score(self) -> Score:
        data = {
            "title": "Simple Flute Tune",
            "tempo_bpm": 80,
            "time_signature": [4, 4],
            "measures": [
                {
                    "notes": [
                        {"pitch": "G#4", "duration_beats": 0.25},
                        {"pitch": "F#4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "Eb4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
                                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
                    ]
                },
                           {
                    "notes": [
                        {"pitch": "G#4", "duration_beats": 0.25},
                        {"pitch": "F#4", "duration_beats": 0.25},
                        {"pitch": "F#4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "C#5", "duration_beats": 1.0},
                        {"pitch": "D#5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F#5", "duration_beats": 4.0}
                    ]
                },
                                {
                    "notes": [
                        {"pitch": "G4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "E4", "duration_beats": 0.25},
                        {"pitch": "F4", "duration_beats": 0.25},
                        {"pitch": "C5", "duration_beats": 1.0},
                        {"pitch": "D5", "duration_beats": 2.0},
                    ]
                },
                {
                    "notes": [
                        {"pitch": "F5", "duration_beats": 4.0}
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
            self.score,
            self.audio,
            self.transport,
            self.main_clip,
            self._player_update_callback,
        )

        # NEW: connect both to Session
        self.session.attach_metronome(self.metronome)
        self.session.attach_player(self.player)
        self.session.initialize_loop_region()

        # Staff initial score
        self.widgets.set_score(self.editor.score)
        
        
    
    # ====== UI update glue =====================================

    def _player_update_callback(self, current_idx, _notes_flat) -> None:
        """Called by PlaybackController when playback advances."""
        self.editor.set_selection_index(current_idx)
        #self.update_ui(current_idx)
        self.widgets.highlight_note(current_idx)

    
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
                beat_start_str = beat_label_from_zero_based(beat_start)
                beat_end_str = beat_label_from_zero_based(beat_end)

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
        beat_start_str = beat_label_from_zero_based(beat_start)
        beat_end_str = beat_label_from_zero_based(beat_end)

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
        self.widgets.scroll_to_note_index(idx)
        self._update_status_from_index(idx)

    # ====== Menu / file actions ================================
        # ====== Menu / file actions ================================
    def on_open_project(self) -> None:
        self.file_actions.open_project()

    def on_open(self) -> None:
        self.file_actions.open_score()

    def on_save_project_as(self) -> None:
        self.file_actions.save_project_as()

    def on_save_as(self) -> None:
        self.file_actions.save_score_as()

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
        # Let the session propagate to score + transport + metronome
        self.session.set_tempo(bpm)

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
        now = time.perf_counter()
        last = getattr(self, "_last_transport_time", now)
        dt = now - last
        self._last_transport_time = now

        # Now session owns the engine time progression
        self.session.process_tick(dt)

        self.root.after(20, self._transport_tick)

   
    def select_interval_for_current_note(self) -> None:
        """
        Use the currently selected note as an interval selection
        (its beat range in its measure).
        """
        changed = self.session.select_interval_for_current_note()
        if changed:
            self.update_ui()

    def clear_interval_selection(self) -> None:
        """
        Return to note-selection mode (keep current selected note).
        """
        self.session.clear_interval_selection()
        self.update_ui()

   
    def on_start(self) -> None:
        if not self.session.has_notes():
            return

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(self.session.play_from_beginning)
        else:
            self.session.play_from_beginning()

    def on_play_from_selected(self) -> None:
        if not self.session.has_notes():
            return

        def _do():
            self.session.play_from_selection()

        if self._stick_to_next_bar_enabled():
            self._schedule_on_next_bar(_do)
        else:
            _do()

    def on_pause(self) -> None:
        self.session.pause()

    def on_stop(self) -> None:
        self.session.stop()
        # Selection is reset by Session.stop; just refresh UI
        self.update_ui(0)
        
    def set_loop_in_at_selection(self) -> None:
        self.session.set_loop_in_at_selection()

    def set_loop_out_at_selection(self) -> None:
        self.session.set_loop_out_at_selection()

    def on_toggle_loop(self) -> None:
        enabled = self.widgets.loop_var.get()
        self.session.set_loop_enabled(enabled)


    def _stick_to_next_bar_enabled(self) -> bool:
        # Safe guard in case widgets aren't fully initialized
        return bool(getattr(self.widgets, "stick_to_bar_var", None) and self.widgets.stick_to_bar_var.get())

    def _schedule_on_next_bar(self, callback: Callable[[], None]) -> None:
        """
        Call `callback` aligned so that it starts exactly on beat 1
        of the next bar, according to Session/metronome info.

        If 'stick to next bar' is disabled or alignment info is unavailable,
        call immediately.
        """
        # If stick-to-next-bar is off, just run now
        if not self._stick_to_next_bar_enabled():
            callback()
            return

        now_ms = int(time.time() * 1000)
        delay_ms = self.session.compute_next_bar_delay_ms(now_ms)

        if delay_ms is None:
            # No reliable alignment info → run immediately
            callback()
            return

        self.root.after(delay_ms, callback)

    # ====== Editing (selection + pitch) ========================

    def move_selection(self, delta: int) -> None:
        new_idx = self.session.move_selection(delta)
        if new_idx is not None:
            self.widgets.highlight_note(new_idx)
            
    def change_selected_pitch(self, delta_steps: int) -> None:
        if self.player is None or not self.player.notes_flat:
            return

        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=transpose_pitch_diatonic,
        )

        if new_idx is None:
            return

        # 1) Sync UI score
        self.widgets.set_score(self.score)

        # 2) Sync playback's view of notes for UI highlighting
        self.player.notes_flat = self.editor.get_flat_notes()

        # 3) Sync active MidiClip events so AUDIO matches edited score
        self.session.sync_active_midi_clip_from_score()

        # 5) Update UI selection
        self.update_ui(new_idx)

    # ====== Key binds ========================
    
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
