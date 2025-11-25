# score.py
from dataclasses import dataclass
from typing import List, Dict, Any

@dataclass
class Note:
    pitch: str
    duration_beats: float

@dataclass
class Measure:
    notes: List[Note]

@dataclass
class Score:
    title: str
    tempo_bpm: int
    time_signature: tuple[int, int]
    measures: List[Measure]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Score":
        measures = []
        for m in data["measures"]:
            notes = [Note(n["pitch"], n["duration_beats"]) for n in m["notes"]]
            measures.append(Measure(notes))
        return cls(
            title=data.get("title", "Untitled"),
            tempo_bpm=data.get("tempo_bpm", 80),
            time_signature=tuple(data.get("time_signature", [4, 4])),
            measures=measures,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "tempo_bpm": self.tempo_bpm,
            "time_signature": list(self.time_signature),
            "measures": [
                {"notes": [
                    {"pitch": n.pitch, "duration_beats": n.duration_beats}
                    for n in measure.notes
                ]}
                for measure in self.measures
            ],
        }

    def all_notes(self):
        for mi, measure in enumerate(self.measures):
            for ni, note in enumerate(measure.notes):
                yield mi, ni, note
