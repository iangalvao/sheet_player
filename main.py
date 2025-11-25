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

    # Staff view (above the text label, or wherever you prefer)
    staff_view = StaffView(root, width=800, height=160)
    staff_view.pack(pady=5)
    staff_view.set_score(score)

    label = tk.Label(root, font=("Arial", 24))
    label.pack(pady=10)
    
    def update_ui(current_idx, notes_flat):
        # Text list of notes
        parts = []
        for i, (_, _, note) in enumerate(notes_flat):
            parts.append(f"[{note.pitch}]" if i == current_idx else note.pitch)
        label.config(text=" ".join(parts))

        # Staff highlight
        staff_view.highlight_note(current_idx)

    player = PlaybackController(root, score, audio, update_ui)

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

    tk.Checkbutton(
        metro_frame,
        text="On",
        variable=metro_on_var,
        command=on_toggle_metronome
    ).pack(side=tk.LEFT)



    # === Menu: Open / Save ===
    menubar = tk.Menu(root)
    filemenu = tk.Menu(menubar, tearoff=0)

    def on_open():
        nonlocal score, player
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
        player = PlaybackController(root, score, audio, update_ui)
        metronome.set_tempo(score.tempo_bpm)
        metronome.set_beats_per_bar(score.time_signature[0])
        staff_view.set_score(score) 
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
