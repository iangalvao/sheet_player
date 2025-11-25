# main.py
import tkinter as tk
from tkinter import filedialog, messagebox
import json

from score import Score
from audio_engine import AudioEngine
from player import PlaybackController
from metronome import Metronome

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
                {"pitch": "G4", "duration_beats": 2.0},
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

    label = tk.Label(root, font=("Arial", 24))
    label.pack(pady=10)

    def update_ui(current_idx, notes_flat):
        parts = []
        for i, (_, _, note) in enumerate(notes_flat):
            parts.append(f"[{note.pitch}]" if i == current_idx else note.pitch)
        label.config(text=" ".join(parts))

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
    tk.Button(controls, text="Pause", command=player.pause).pack(side=tk.LEFT, padx=5)
    tk.Button(controls, text="Stop", command=player.stop).pack(side=tk.LEFT, padx=5)

    update_ui(0, player.notes_flat)
    root.mainloop()

if __name__ == "__main__":
    main()
