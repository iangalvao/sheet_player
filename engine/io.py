# maybe in ui/app.py or engine/io.py
import json
from pathlib import Path
from typing import Tuple

from domain.score import Score
from engine.project import Project


def load_project_or_score(path: str | Path) -> Tuple[Project, Score]:
    """
    - If JSON has 'tracks' → interpret as Project; derive Score from first MIDI clip's 'score' field.
    - Else → interpret as legacy Score JSON; wrap into a one-track Project.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # New project format
    if "tracks" in data:
        project = Project.from_dict(data)

        # Find first MIDI track & its first clip
        if not project.tracks:
            raise ValueError("Project has no tracks")

        midi_track = None
        for t in project.tracks:
            if t.track_type == Project.TrackType.MIDI if hasattr(Project, "TrackType") else True:
                midi_track = t
                break
        if midi_track is None:
            midi_track = project.tracks[0]

        if not midi_track.clips:
            raise ValueError("MIDI track has no clips")

        clip_dicts = data["tracks"][project.tracks.index(midi_track)]["clips"]
        first_clip_dict = clip_dicts[0]
        score_dict = first_clip_dict.get("score")
        if not score_dict:
            raise ValueError("Project clip has no embedded 'score'")

        score = Score.from_dict(score_dict)
        return project, score

    # Legacy score format: wrap into project
    else:
        score = Score.from_dict(data)
        project = Project.from_score(score, track_name=score.title or "Flute")
        return project, score

def save_project_to_json(path: str | Path, project: Project, score: Score) -> None:
    data = project.to_dict(score_for_first_midi_track=score)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
