15 results - 10 files

domain/editor.py:
  19:     def __init__(self, score: Score):
  20:         self.score: Score = score
  21:         self.selected_index: int = 0
  22:         # (measure_idx, note_idx, Note)
  23:         self._notes_flat: List[Tuple[int, int, object]] = []
  24:         self._rebuild_flat()
  25: 
  26:         # Selection mode: "note" or "interval"
  27:         self._selection_mode: str = "note"
  28:         # (measure_index, beat_start, beat_end)
  29:         self._selection_interval: Optional[Tuple[int, BeatTime, BeatTime]] = None
  30: 
  31:     # ----- internal helpers ------------------------------------
  32: 

engine/audio_engine.py:
  49:     def __init__(self, sample_rate: int = SAMPLE_RATE):
  50:         self.sample_rate = sample_rate
  51: 
  52:         # note voice
  53:         self._note_wave: Optional[np.ndarray] = None
  54:         self._note_index: int = 0
  55:         self._note_active: bool = False
  56: 
  57:         # click voice
  58:         self._click_wave: Optional[np.ndarray] = None
  59:         self._click_index: int = 0
  60:         self._click_active: bool = False
  61: 
  62:         self._lock = threading.Lock()
  63: 
  64:         self._stream = sd.OutputStream(
  65:             samplerate=self.sample_rate,
  66:             channels=1,
  67:             dtype="float32",
  68:             callback=self._callback,
  69:         )
  70:         self._stream.start()
  71: 
  72:     # ---------- helpers ----------
  73: 

engine/metronome.py:
   8:     def __init__(self,
   9:                  root,
  10:                  audio: AudioEngine,
  11:                  tempo_bpm: int = 80,
  12:                  beats_per_bar: int = 4,
  13:                  visual_callback: Optional[Callable[[bool], None]] = None):
  14:         self.root = root
  15:         self.audio = audio
  16:         self.tempo_bpm = tempo_bpm
  17:         self.beats_per_bar = beats_per_bar
  18:         self.visual_callback = visual_callback
  19: 
  20:         self.is_running = False
  21:         self.current_beat = 0  # 1..beats_per_bar
  22:         self.last_beat_time_ms: Optional[int] = None
  23: 

engine/player.py:
  22:     def __init__(
  23:         self,
  24:         root,
  25:         score: Score,
  26:         audio: AudioEngine,
  27:         transport: Transport,
  28:         clip: MidiClip,
  29:         update_ui: Callable[[int, list], None],
  30:     ) -> None:
  31:         self.root = root
  32:         self.score = score
  33:         self.audio = audio
  34:         self.transport = transport
  35:         self.clip = clip
  36:         self.update_ui = update_ui
  37: 
  38:         # Flat (measure_index, note_index, Note) list for UI
  39:         self.notes_flat: List[Tuple[int, int, object]] = list(score.all_notes())
  40: 
  41:         # Playback state
  42:         self.is_playing: bool = False
  43: 
  44:         # Loop in terms of indices (for now)
  45:         self.loop_enabled: bool = False
  46:         self.loop_start_index: int = 0
  47:         self.loop_end_index: int = max(0, len(self.notes_flat) - 1)
  48:         self.loop_start_beats = 0.0
  49:         self.loop_end_beats = (
  50:             self.clip.events[self.loop_end_index].start_beats
  51:             + self.clip.events[self.loop_end_index].duration_beats
  52:             if self.clip.events else 0.0
  53:         )
  54: 
  55: 
  56:         # Internal event pointer & time tracking
  57:         self._next_event_index: int = 0
  58:         self._last_processed_beats: Optional[float] = None
  59: 
  60:     # ------------------------------------------------------------------
  61:     # Score / clip reset
  62:     # ------------------------------------------------------------------
  63:     def reset_score(self, score: Score, clip: MidiClip) -> None:

engine/session.py:
  22:     def __init__(
  23:         self,
  24:         score: Score,
  25:         editor: EditorController,
  26:         player: Optional[PlaybackController] = None,
  27:     ) -> None:
  28:         self.score = score
  29:         self.editor = editor
  30:         self.player: Optional[PlaybackController] = player
  31: 
  32:         # Loop region in terms of flat-note indices
  33:         self.loop_start_index: int = 0
  34:         self.loop_end_index: int = 0
  35: 
  36:     # --- wiring -------------------------------------------------
  37: 

engine/transport.py:
  65:     def __init__(self, transport: Transport) -> None:
  66:         self.transport = transport
  67:         self._events: List[Tuple[float, Callable[[], None]]] = []
  68: 

ui/app.py:
  42:     def __init__(self) -> None:
  43:         self.root = tk.Tk()
  44:         self.root.title("Flute Practice Prototype")
  45: 
  46:         # Core state
  47:         self.score: Score = self._make_demo_score()
  48:         self.project: Project | None = None
  49:         self.main_track: Track | None = None
  50:         self.main_clip = None 
  51:                 # After self.score and self.project are ready:
  52:         self.transport = Transport(
  53:             tempo_bpm=self.score.tempo_bpm,
  54:             time_signature=self.score.time_signature,
  55:         )
  56:         self.scheduler = Scheduler(self.transport)
  57:         # Keep the transport clock running; we use it as a global musical timeline.
  58: 
  59:         self.audio = AudioEngine()
  60:         self.player: PlaybackController | None = None
  61:         self.metronome: Metronome | None = None
  62:         self.editor = EditorController(self.score)
  63: 
  64: 
  65:         # Build project based on initial score
  66:         self._build_project_from_score()
  67: 
  68: 
  69:         # Editor state        
  70:         self.session = Session(self.score, self.editor)
  71:         self.on_toggle_stick_to_bar = False
  72:         # UI
  73:         self.widgets: WidgetsType = Widgets(self.root, self)
  74: 
  75:         # Engines (metronome + player)
  76:         self._init_engines()
  77:         self.transport.play()
  78: 
  79:         # Key bindings
  80:         self.root.bind_all("<Key>", self.on_key)
  81:         # Initial UI sync
  82:         self._start_transport_loop()
  83:         self.update_ui(0)
  84: 
  85:     # ====== Setup helpers ======================================
  86: 

ui/staff_view.py:
  21:     def __init__(self, master, width: int = 800, height: int = 160, **kwargs):
  22:         super().__init__(master, width=width, height=height, bg="white", **kwargs)
  23:         self.score: Optional[Score] = None
  24: 
  25:         # Flattened note positions: one per note in score.all_notes() order
  26:         self.note_positions: List[Tuple[float, float]] = []
  27: 
  28:         # Index of currently highlighted note in note_positions (or -1 for none)
  29:         self.highlight_index: int = -1
  30: 
  31:         # Selection region for overlay: (measure_index, beat_start, beat_end)
  32:         self.selection_region: Optional[Tuple[int, float, float]] = None
  33: 
  34:         # Layout parameters
  35:         self.left_margin = 40
  36:         self.right_margin = 20
  37:         self.top_margin = 20
  38:         self.bottom_margin = 20
  39: 
  40:         # Pitch mapping reference
  41:         self._letter_order = ["C", "D", "E", "F", "G", "A", "B"]
  42:         # We'll treat B4 as the middle staff line (step = 0)
  43:         self._ref_pitch = "B4"
  44: 
  45:     # ===== External API ========================================
  46: 

ui/widgets.py:
  21:     def __init__(self, root: tk.Tk, app: "App") -> None:
  22:         self.root = root
  23:         self.app = app
  24: 
  25:         # === Menu: File ===
  26:         menubar = tk.Menu(root)
  27:         filemenu = tk.Menu(menubar, tearoff=0)
  28:         filemenu.add_command(label="Open...", command=self.app.on_open)
  29:         filemenu.add_command(label="Save As...", command=self.app.on_save_as)
  30:         filemenu.add_separator()
  31:         filemenu.add_command(label="Quit", command=self.app.on_quit)
  32:         menubar.add_cascade(label="File", menu=filemenu)
  33:         root.config(menu=menubar)
  34: 
  35:         # === Staff view + note label ===
  36:         self.staff_view = StaffView(root, width=800, height=160)
  37:         self.staff_view.pack(pady=5)
  38:         self.staff_view.set_score(app.score)
  39: 
  40:         self.note_label = tk.Label(root, font=("Arial", 24))
  41:         self.note_label.pack(pady=10)
  42: 
  43:         # === Metronome panel ===
  44:         metro_frame = tk.Frame(root)
  45:         metro_frame.pack(pady=5)
  46: 
  47:         tk.Label(metro_frame, text="Metronome:").pack(side=tk.LEFT)
  48: 
  49:         self.metro_canvas = tk.Canvas(metro_frame, width=24, height=24, highlightthickness=0)
  50:         self.metro_canvas.pack(side=tk.LEFT, padx=5)
  51:         self._beat_circle = self.metro_canvas.create_oval(
  52:             4, 4, 20, 20, fill="grey", outline="black"
  53:         )
  54: 
  55:         self.metro_on_var = tk.BooleanVar(value=False)
  56:         tk.Checkbutton(
  57:             metro_frame,
  58:             text="On",
  59:             variable=self.metro_on_var,
  60:             command=self.app.on_toggle_metronome,
  61:         ).pack(side=tk.LEFT)
  62: 
  63:         # === Tempo control ===
  64:         tempo_frame = tk.Frame(root)
  65:         tempo_frame.pack(pady=5)
  66:         tk.Label(tempo_frame, text="Tempo (bpm):").pack(side=tk.LEFT)
  67: 
  68:         self.tempo_var = tk.StringVar(value=str(app.score.tempo_bpm))
  69: 
