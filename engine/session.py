# engine/session.py
from __future__ import annotations

from typing import Optional

from domain.score import Score
from domain.editor import EditorController
from engine.player import PlaybackController
from engine.timebase import compute_next_bar_start_time_ms
from engine.transport import Transport, Scheduler
from engine.metronome import Metronome
from domain.theory import transpose_pitch_diatonic
from engine.project import Clip, Project, Track, MidiClip


class Session:
    """
    Engine-level facade for the DAW state.

    Owns / coordinates:
      - Score + Editor
      - Transport + Scheduler
      - Metronome
      - PlaybackController
      - (Optionally) a Project with multiple tracks/clips
    """

    def __init__(
        self,
        score: Score,
        editor: EditorController,
        transport: Transport,
        scheduler: Scheduler,
        metronome: Optional[Metronome] = None,
        player: Optional[PlaybackController] = None,
        project: Optional[Project] = None,
    ) -> None:
        self.score = score
        self.editor = editor

        self.transport = transport
        self.scheduler = scheduler
        self.metronome: Optional[Metronome] = metronome
        self.player: Optional[PlaybackController] = player

        # Project / tracks / clips
        self.project: Optional[Project] = project
        self.active_track_index: int = 0
        self.active_clip_index: int = 0

        if self.project is not None:
            self._normalize_active_indices()
    # --- wiring -------------------------------------------------

    def attach_player(self, player: PlaybackController) -> None:
        self.player = player

    def attach_metronome(self, metronome: Metronome) -> None:
        self.metronome = metronome

    def has_notes(self) -> bool:
        return self.player is not None and bool(self.player.notes_flat)
    
        # --- project / tracks / clips -------------------------------

    def _normalize_active_indices(self) -> None:
        """
        Keep active_track_index / active_clip_index within bounds.
        For now we just clamp to 0 if the project is empty.
        """
        if self.project is None or not self.project.tracks:
            self.active_track_index = 0
            self.active_clip_index = 0
            return

        # Clamp track index
        if self.active_track_index < 0:
            self.active_track_index = 0
        if self.active_track_index >= len(self.project.tracks):
            self.active_track_index = len(self.project.tracks) - 1

        track = self.project.tracks[self.active_track_index]
        if not track.clips:
            self.active_clip_index = 0
            return

        # Clamp clip index
        if self.active_clip_index < 0:
            self.active_clip_index = 0
        if self.active_clip_index >= len(track.clips):
            self.active_clip_index = len(track.clips) - 1

    def set_project(
        self,
        project: Optional[Project],
        active_track_index: int = 0,
        active_clip_index: int = 0,
    ) -> None:
        """
        Replace the current Project and set active track/clip indices.

        For now this does NOT automatically change `score` / `editor` / `player`;
        App still manages those. Later we can make this choose the score/clip
        from the active track.
        """
        self.project = project
        self.active_track_index = active_track_index
        self.active_clip_index = active_clip_index
        if self.project is not None:
            self._normalize_active_indices()

    def set_active_track(self, idx: int) -> None:
        self.active_track_index = idx
        self._normalize_active_indices()

    def set_active_clip(self, idx: int) -> None:
        self.active_clip_index = idx
        self._normalize_active_indices()

    def get_active_track(self) -> Optional[Track]:
        if self.project is None or not self.project.tracks:
            return None
        self._normalize_active_indices()
        return self.project.tracks[self.active_track_index]

    def get_active_clip(self) -> Optional[Clip]:
        """
        Return the currently active Clip (may be MidiClip or another Clip subclass).
        """
        track = self.get_active_track()
        if track is None or not track.clips:
            return None
        self._normalize_active_indices()
        return track.clips[self.active_clip_index]

    def get_active_midi_clip(self) -> Optional[MidiClip]:
        """
        Convenience for the common '1 MIDI track' case.
        Returns None if the active track is not MIDI or has no MidiClip.
        """
        clip = self.get_active_clip()
        if isinstance(clip, MidiClip):
            return clip
        return None


    # --- global time / tempo -----------------------------------

    def compute_next_bar_delay_ms(self, now_ms: int) -> Optional[int]:
        """
        Compute how many milliseconds to wait until the start of the next bar,
        based on the metronome's last beat info and the current tempo / time signature.

        Returns:
          - delay in ms (>= 0) if we can align to the next bar
          - None if we don't have enough info (no metronome, not running, etc.)
        """
        if self.metronome is None or not self.metronome.is_running:
            return None

        beats_per_bar = self.score.time_signature[0]
        if beats_per_bar <= 0:
            return None

        current_beat, last_beat_time_ms = self.metronome.get_last_beat_info()
        if last_beat_time_ms is None:
            return None

        target_time_ms = compute_next_bar_start_time_ms(
            tempo_bpm=self.score.tempo_bpm,
            beats_per_bar=beats_per_bar,
            current_beat_in_bar=current_beat,
            last_beat_time_ms=last_beat_time_ms,
            now_ms=now_ms,
        )
        delay_ms = max(0, target_time_ms - now_ms)
        return delay_ms


    def process_tick(self, dt_seconds: float) -> None:
        """
        Advance musical time and let scheduled engine callbacks fire.
        This should be called regularly by the UI (e.g. every 20ms).
        """
        # 1) advance musical time
        self.transport.tick(dt_seconds)

        # 2) trigger any scheduled musical events
        self.scheduler.process()

        # 3) let the playback controller react to the new time
        if self.player is not None:
            self.player.process_tick()

    def set_tempo(self, bpm: int) -> None:
        """
        Set score tempo and propagate to transport + metronome.
        """
        self.score.tempo_bpm = bpm
        self.transport.set_tempo(bpm)
        if self.metronome is not None:
            self.metronome.set_tempo(bpm)

    def set_time_signature(self, ts: tuple[int, int]) -> None:
        """
        Set score time signature and propagate to transport + metronome.
        """
        self.score.time_signature = ts
        self.transport.set_time_signature(ts)
        if self.metronome is not None:
            self.metronome.set_beats_per_bar(ts[0])

    # --- loop management ----------------------------------------

    def initialize_loop_region(self) -> None:
        """
        Default loop: the whole song (all notes) if any.
        """
        if self.player is None or not self.player.notes_flat:
            return

        self.loop_start_index = 0
        self.loop_end_index = len(self.player.notes_flat) - 1
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_in_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_start_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_end_index = self.loop_start_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_out_at_selection(self) -> None:
        if not self.has_notes():
            return
        idx = self.editor.get_selection_index()
        if idx is None:
            return

        self.loop_end_index = idx
        if self.loop_end_index < self.loop_start_index:
            self.loop_start_index = self.loop_end_index

        assert self.player is not None
        self.player.set_loop_region(self.loop_start_index, self.loop_end_index)

    def set_loop_enabled(self, enabled: bool) -> None:
        if self.player is None:
            return
        self.player.set_loop_enabled(enabled)

    # --- playback controls --------------------------------------

    def play_from_beginning(self) -> None:
        if self.player is None:
            return
        self.player.play_from_beginning()

    def play_from_selection(self) -> None:
        if not self.has_notes():
            return

        idx = self.editor.get_selection_index()
        if idx is None:
            return

        assert self.player is not None
        self.player.play_from_index(idx)

    def pause(self) -> None:
        if self.player is None:
            return
        self.player.pause()

    def stop(self) -> None:
        if self.player is None:
            return
        self.player.stop()
        # Reset selection to the first note (if any)
        self.editor.set_selection_index(0)

    # --- selection / editing ------------------------------------

    def move_selection(self, delta: int) -> Optional[int]:
        """
        Move note selection by +1 / -1, etc.
        Returns the new index or None if it did not change.
        """
        if not self.has_notes():
            return None

        new_idx = self.editor.move_selection(delta)
        return new_idx

    def transpose_selected(self, delta_steps: int) -> Optional[int]:
        """
        Transpose the currently selected note diatonically.
        Returns the new selected index, or None if nothing changed.

        This mutates the underlying Score via EditorController.
        """
        if not self.has_notes():
            return None

        # Assumes EditorController.transpose_selected(delta, transpose_pitch_func=...)
        new_idx = self.editor.transpose_selected(
            delta_steps,
            transpose_pitch_func=transpose_pitch_diatonic,
        )
        return new_idx

    def sync_active_midi_clip_from_score(self) -> None:
        """
        Sync the pitches in the active MidiClip from the current Score/editor.

        Assumes:
          - editor._notes_flat and clip.events correspond 1:1 in order.
        """
        clip = self.get_active_midi_clip()
        if clip is None:
            return

        flat = self.editor.get_flat_notes()
        events = clip.events

        n = min(len(flat), len(events))
        for i in range(n):
            _mi, _ni, note = flat[i]
            events[i].pitch = note.pitch


    # --- interval selection -------------------------------------

    def select_interval_for_current_note(self) -> bool:
        """
        Use the currently selected note as an interval selection.

        Returns True if an interval was selected, False otherwise.
        """
        idx = self.editor.get_selection_index()
        if idx is None:
            return False

        interval = self.editor.select_interval_for_index(idx)
        return interval is not None

    def clear_interval_selection(self) -> None:
        self.editor.clear_interval_selection()
