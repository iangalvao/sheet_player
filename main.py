# main.py
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import json

from score import Score
from audio_engine import AudioEngine
from player import PlaybackController
from metronome import Metronome
from staff_view import StaffView   # NEW

def load_score_from_json(path: str) -> Score:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Score.from_dict(data)

def save_score_to_json(score: Score, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(score.to_dict(), f, indent=2)

def make_demo_score() -> Score:
    data = {
        "title": "Simple Flute Tune",
        "tempo_bpm": 80,
        "time_signature": [4, 4],
        "measures": [
            {"notes": [
                {"pitch": "G4", "duration_beats": 1.0},
                {"pitch": "C5", "duration_beats": 1.0},
                {"pitch": "D5", "duration_beats": 1.0},
                {"pitch": "E5", "duration_beats": 1.0},
            ]},
            {"notes": [
                {"pitch": "F5", "duration_beats": 1.0},
                {"pitch": "E5", "duration_beats": 1.0},
                {"pitch": "D5", "duration_beats": 1.0},
                {"pitch": "C5", "duration_beats": 1.0},
            ]},
        ],
    }
    return Score.from_dict(data)

def main():
    root = tk.Tk()
    root.title("Flute Practice Prototype")

    score = make_demo_score()
    audio = AudioEngine()

     # Staff view
    staff_view = StaffView(root, width=800, height=160)
    staff_view.pack(pady=5)
    staff_view.set_score(score)

    label = tk.Label(root, font=("Arial", 24))
    label.pack(pady=10)

    # selection state
    selected_index = 0

    # === Status ===
    status_var = tk.StringVar(value="Ready")
    status_label = tk.Label(root, textvariable=status_var, anchor="w")
    status_label.pack(fill="x", side=tk.BOTTOM, padx=5, pady=3)

    def update_status():
        nonlocal selected_index

        if not player.notes_flat:
            status_var.set("No notes in score")
            return

        # Clamp index just in case
        idx = max(0, min(len(player.notes_flat) - 1, selected_index))
        mi, ni, note = player.notes_flat[idx]

        # Compute approximate beat position in the measure
        measure = score.measures[mi]
        beat_pos = 0.0
        for j, n in enumerate(measure.notes):
            if j == ni:
                break
            beat_pos += n.duration_beats

        center_beat = beat_pos + measure.notes[ni].duration_beats / 2.0

        status_var.set(
            f"Measure {mi + 1}, note {ni + 1}, beat ~{center_beat:.2f}, pitch {note.pitch}"
        )


    def update_ui(current_idx, notes_flat):
        nonlocal selected_index
        selected_index = current_idx
        parts = []
        for i, (_, _, note) in enumerate(notes_flat):
            parts.append(f"[{note.pitch}]" if i == selected_index else note.pitch)
        label.config(text=" ".join(parts))
        staff_view.highlight_note(selected_index)
        update_status()


    player = PlaybackController(root, score, audio, update_ui)
    update_ui(0, player.notes_flat)

    # === Metronome visual indicator ===
    metro_frame = tk.Frame(root)
    metro_frame.pack(pady=5)

    tk.Label(metro_frame, text="Metronome:").pack(side=tk.LEFT)

    metro_canvas = tk.Canvas(metro_frame, width=24, height=24, highlightthickness=0)
    metro_canvas.pack(side=tk.LEFT, padx=5)
    beat_circle = metro_canvas.create_oval(4, 4, 20, 20, fill="grey", outline="black")

    def metro_visual(strong: bool):
        color = "tomato" if strong else "gold"
        metro_canvas.itemconfig(beat_circle, fill=color)
        # fade back to grey after a short delay
        root.after(80, lambda: metro_canvas.itemconfig(beat_circle, fill="grey"))

    beats_per_bar = score.time_signature[0]
    metronome = Metronome(
        root,
        audio,
        tempo_bpm=score.tempo_bpm,
        beats_per_bar=beats_per_bar,
        visual_callback=metro_visual,
    )

    metro_on_var = tk.BooleanVar(value=False)

    def on_toggle_metronome():
        if metro_on_var.get():
            metronome.set_tempo(score.tempo_bpm)
            metronome.set_beats_per_bar(score.time_signature[0])
            metronome.start()
        else:
            metronome.stop()
    def start_on_next_bar():
        """
        Start playback aligned so that the FIRST note lands exactly on
        beat 1 of the next bar (if metronome is on).

        Uses the metronome's last beat timestamp for more precise alignment.
        """
        # If metronome is running, sync to it
        if metro_on_var.get() and metronome.is_running:
            beat_interval_ms = int(60000 / score.tempo_bpm)
            current_beat, last_beat_time_ms = metronome.get_last_beat_info()
            bpb = metronome.beats_per_bar

            # If we never had a beat yet, just wait one full bar from now
            if current_beat == 0 or last_beat_time_ms is None:
                beats_remaining = bpb
                now_ms = int(time.time() * 1000)
                target_time_ms = now_ms + beats_remaining * beat_interval_ms
            else:
                # Example: on beat 3 of 4 → remaining = (4 - 3 + 1) = 2 beats
                beats_remaining = (bpb - current_beat + 1)
                target_time_ms = last_beat_time_ms + beats_remaining * beat_interval_ms

            now_ms = int(time.time() * 1000)
            delay_ms = max(0, target_time_ms - now_ms)
            root.after(delay_ms, player.play)
        else:
            # No metronome → start immediately
            player.play()

    LETTER_ORDER = ["C", "D", "E", "F", "G", "A", "B"]

    # Diatonic index bounds for E4..F5
    # index = LETTER_ORDER.index(letter) + 7 * octave
    MIN_DIATONIC_INDEX = LETTER_ORDER.index("E") + 7 * 4   # E4
    MAX_DIATONIC_INDEX = LETTER_ORDER.index("F") + 7 * 5   # F5


    def pitch_to_diatonic_index(pitch: str) -> int:
        """
        Map a pitch like 'G4' to a diatonic index:
        index = LETTER_ORDER.index(letter) + 7 * octave

        Accidentals are ignored for the index.
        """
        up = pitch.upper()
        if up == "REST":
            # treat rests as out-of-range sentinel
            return MIN_DIATONIC_INDEX

        i = 0
        while i < len(pitch) and not pitch[i].isdigit():
            i += 1
        name = pitch[:i]
        octave_str = pitch[i:] or "4"

        letter = name[0].upper()
        octave = int(octave_str)

        if letter not in LETTER_ORDER:
            return MIN_DIATONIC_INDEX

        return LETTER_ORDER.index(letter) + 7 * octave


    def diatonic_index_to_pitch(index: int) -> str:
        """
        Inverse of pitch_to_diatonic_index for naturals:
        given index, return 'C4' style string.
        """
        octave, letter_idx = divmod(index, 7)
        letter = LETTER_ORDER[letter_idx]
        return f"{letter}{octave}"


    def transpose_pitch_diatonic(pitch: str, steps: int) -> str:
        """
        Transpose pitch by diatonic steps, clamped to E4..F5.
        """
        up = pitch.upper()
        if up == "REST":
            return pitch

        idx = pitch_to_diatonic_index(pitch)
        idx_new = idx + steps

        # clamp
        if idx_new < MIN_DIATONIC_INDEX:
            idx_new = MIN_DIATONIC_INDEX
        if idx_new > MAX_DIATONIC_INDEX:
            idx_new = MAX_DIATONIC_INDEX

        return diatonic_index_to_pitch(idx_new)




    tk.Checkbutton(
        metro_frame,
        text="On",
        variable=metro_on_var,
        command=on_toggle_metronome
    ).pack(side=tk.LEFT)


    def move_selection(delta: int):
        nonlocal selected_index
        if not player.notes_flat:
            return
        new_idx = max(0, min(len(player.notes_flat) - 1, selected_index + delta))
        selected_index = new_idx
        update_ui(selected_index, player.notes_flat)

    def change_selected_pitch(delta_steps: int):
        nonlocal selected_index, score, player
        if not player.notes_flat:
            return
        idx = selected_index
        mi, ni, note = player.notes_flat[idx]  # note is a Note object in the Score
        old_pitch = note.pitch
        new_pitch = transpose_pitch_diatonic(old_pitch, delta_steps)
        note.pitch = new_pitch

        # After editing, re-sync staff and flat list
        staff_view.set_score(score)
        player.notes_flat = list(score.all_notes())
        # Keep same index if possible
        if idx >= len(player.notes_flat):
            idx = len(player.notes_flat) - 1
        selected_index = idx
        update_ui(selected_index, player.notes_flat)

    def on_key(event):
        # print(event.keysym)  # you can debug with this if needed
        key = event.keysym

        # A / D for horizontal movement
        if key in ("a", "A"):
            move_selection(-1)
        elif key in ("d", "D"):
            move_selection(1)

        # Up / Down for pitch change
        elif key == "Up":
            change_selected_pitch(+1)
        elif key == "Down":
            change_selected_pitch(-1)

    # Bind keys globally so you don't have to focus specific widget
    root.bind_all("<Key>", on_key)



    # === Menu: Open / Save ===
    menubar = tk.Menu(root)
    filemenu = tk.Menu(menubar, tearoff=0)
    def on_open():
        nonlocal score, player, selected_index
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

        score = new_score
        staff_view.set_score(score)
        player = PlaybackController(root, score, audio, update_ui)
        selected_index = 0
        update_ui(0, player.notes_flat)


    def on_save_as():
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON scores", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            save_score_to_json(score, path)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save score:\n{e}")



    filemenu.add_command(label="Open...", command=on_open)
    filemenu.add_command(label="Save As...", command=on_save_as)
    filemenu.add_separator()
    filemenu.add_command(label="Quit", command=root.quit)
    menubar.add_cascade(label="File", menu=filemenu)
    root.config(menu=menubar)

    # === Tempo control ===
    tempo_frame = tk.Frame(root)
    tempo_frame.pack(pady=5)
    tk.Label(tempo_frame, text="Tempo (bpm):").pack(side=tk.LEFT)
    tempo_var = tk.StringVar(value=str(score.tempo_bpm))

    def on_tempo_change(*_):
        try:
            bpm = int(tempo_var.get())
            bpm = max(20, min(bpm, 300))
            score.tempo_bpm = bpm
            metronome.set_tempo(bpm)
        except ValueError:
            pass

    tempo_entry = tk.Entry(tempo_frame, textvariable=tempo_var, width=5)
    tempo_entry.pack(side=tk.LEFT)
    tempo_var.trace_add("write", on_tempo_change)

    # === Transport ===
    controls = tk.Frame(root)
    controls.pack(pady=10)
    tk.Button(controls, text="Start", command=player.play).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Start next bar", command=start_on_next_bar).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Pause", command=player.pause).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Stop", command=player.stop).pack(side=tk.LEFT, padx=5)


    update_ui(0, player.notes_flat)
    root.mainloop()

if __name__ == "__main__":
    main()
