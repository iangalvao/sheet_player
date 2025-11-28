domain/editor.py:
class EditorController:
    def __init__(self, score: Score):
    def _rebuild_flat(self) -> None:
    def set_score(self, score: Score) -> None:
    def get_flat_notes(self) -> List[Tuple[int, int, object]]:
    def has_notes(self) -> bool:
    def get_selection_mode(self) -> str:
    def clear_interval_selection(self) -> None:
    def get_selection_interval(self) -> Optional[Tuple[int, float, float]]:
    def select_interval_for_index(self, index: int) -> Optional[Tuple[int, float, float]]:
    def get_selected_note_indices(self) -> List[int]:
    def get_selection_index(self) -> Optional[int]:
    def set_selection_index(self, index: int) -> Optional[int]:
    def move_selection(self, delta: int) -> Optional[int]:

domain/score.py:
class Note:
class Measure:
class Score:
    def from_dict(cls, data: Dict[str, Any]) -> "Score":
    def to_dict(self) -> Dict[str, Any]:
    def all_notes(self):
    def total_beats(self) -> float:

engine/audio_engine.py:
class AudioEngine:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
    def play_note(self, pitch: str, duration_s: float, volume: float = 0.25):
    def trigger_click(self, strong: bool = False):
    def close(self):
    def _callback(self, outdata, frames, time, status):

engine/metronome.py:
class Metronome:
    def set_tempo(self, bpm: int):
    def set_beats_per_bar(self, n: int):
    def start(self):
    def stop(self):
    def _schedule_next(self):
    def get_last_beat_info(self) -> tuple[int, Optional[int]]:

engine/player.py:
class PlaybackController:
    def reset_score(self, score: Score, clip: MidiClip) -> None:
    def set_loop_region(self, start_idx: int, end_idx: int) -> None:
    def set_loop_enabled(self, enabled: bool) -> None:
    def _find_event_index_for_beats(self, beats: float) -> int:
    def _wrap_to_loop_start(self) -> None:
    def play_from_beginning(self) -> None:
    def play_from_index(self, index: int | None) -> None:
    def _start_at_index(self, index: int) -> None:
    def play(self) -> None:
    def pause(self) -> None:
    def stop(self) -> None:
    def process_tick(self) -> None:
    def _beats_to_seconds(self, beats: float) -> float:

engine/project.py:
class Clip:
class MidiEvent:
    def to_dict(self) -> Dict[str, Any]:
    def from_dict(cls, data: Dict[str, Any]) -> "MidiEvent":
class MidiClip:
    def to_dict(self, score: Optional[Score] = None) -> Dict[str, Any]:
    def from_dict(cls, data: Dict[str, Any]) -> "MidiClip":
class Track:
    def to_dict(self, score_for_first_clip: Optional[Score] = None) -> Dict[str, Any]:
    def from_dict(cls, data: Dict[str, Any]) -> "Track":
class Project:
    def to_dict(self, score_for_first_midi_track: Optional[Score] = None) -> Dict[str, Any]:
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
    def from_score(cls, score: "Score", track_name: str = "Flute") -> "Project":

engine/session.py:
class Session:
    def attach_player(self, player: PlaybackController) -> None:
    def has_notes(self) -> bool:
    def initialize_loop_region(self) -> None:
    def set_loop_in_at_selection(self) -> None:
    def set_loop_out_at_selection(self) -> None:
    def set_loop_enabled(self, enabled: bool) -> None:
    def play_from_beginning(self) -> None:
    def play_from_selection(self) -> None:
    def pause(self) -> None:
    def stop(self) -> None:
    def move_selection(self, delta: int) -> Optional[int]:
    def transpose_selected(self, delta_steps: int) -> Optional[int]:
    def select_interval_for_current_note(self) -> bool:
    def clear_interval_selection(self) -> None:

engine/timebase.py:
class BeatTime:
    def from_float(cls, value: float, max_denominator: int = 16) -> "BeatTime":
    def to_float(self) -> float:

engine/transport.py:
class Transport:
    def set_tempo(self, bpm: int) -> None:
    def set_time_signature(self, ts: tuple[int, int]) -> None:
    def set_position_beats(self, beats: float) -> None:
    def play(self) -> None:
    def stop(self) -> None:
    def tick(self, dt_seconds: float) -> None:
class Scheduler:
    def __init__(self, transport: Transport) -> None:
    def schedule_at(self, beat: float, callback: Callable[[], None]) -> None:
    def clear(self) -> None:
    def process(self) -> None:

ui/app.py:
class App:
    def __init__(self) -> None:
    def _build_project_from_score(self) -> None:
    def _make_demo_score(self) -> Score:
    def _init_engines(self) -> None:
    def _beat_to_fraction_str(self, beat_zero_based: float) -> str:
    def _player_update_callback(self, current_idx, _notes_flat) -> None:
    def _update_status_from_index(self, idx: int) -> None:
    def update_ui(self, current_idx: int | None = None) -> None:
    def on_open_project(self) -> None:
    def on_open(self) -> None:
    def on_save_project_as(self) -> None:
    def on_save_as(self) -> None:
    def on_quit(self) -> None:
    def on_toggle_metronome(self) -> None:
    def on_tempo_change(self, raw_value: str) -> None:
    def _start_transport_loop(self) -> None:
    def _transport_tick(self) -> None:
    def select_interval_for_current_note(self) -> None:
    def clear_interval_selection(self) -> None:
    def on_start(self) -> None:
    def on_play_from_selected(self) -> None:
    def _do():
    def on_pause(self) -> None:
    def on_stop(self) -> None:
    def set_loop_in_at_selection(self) -> None:
    def set_loop_out_at_selection(self) -> None:
    def on_toggle_loop(self) -> None:
    def _stick_to_next_bar_enabled(self) -> bool:
    def _schedule_on_next_bar(self, callback: Callable[[], None]) -> None:
    def move_selection(self, delta: int) -> None:
    def change_selected_pitch(self, delta_steps: int) -> None:
    def on_key(self, event) -> None:
    def run(self) -> None:

ui/staff_view.py:
    def __init__(self, master, width: int = 800, height: int = 160, **kwargs):
    def set_score(self, score: Score) -> None:
    def highlight_note(self, index: int) -> None:
    def set_selection_region(self, measure_index: int, beat_start: float, beat_end: float) -> None:
    def _pitch_to_staff_step(self, pitch: str) -> int:
    def _recompute_note_positions(self) -> None:
    def _redraw(self) -> None:
    def _draw_staff(self) -> None:
    def _draw_selection_overlay(self) -> None:
    def _draw_notes(self) -> None:

ui/widgets.py:
class Widgets:
    def __init__(self, root: tk.Tk, app: "App") -> None:
    def _tempo_changed(*_):
    def metro_visual(self, strong: bool) -> None:
    def set_score(self, score: Score) -> None:
    def set_note_list(self, text: str) -> None:
    def highlight_note(self, index: int) -> None:
    def set_status(self, text: str) -> None:
    def set_selection_region(self, measure_index: int, beat_start: float, beat_end: float) -> None:
