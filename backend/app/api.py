from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.app.schemas.edit_plan import EditPlan
from backend.app.services.media import probe_video
from backend.app.services.renderer import render_clean_cut
from backend.app.services.retakes import find_retakes
from backend.app.services.transcript_utils import normalize_whisperx
from backend.app.services.transcription import transcribe


router = APIRouter()

STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "storage"))
UPLOADS = STORAGE_ROOT / "uploads"
PROCESSED = STORAGE_ROOT / "processed"
EXPORTS = STORAGE_ROOT / "exports"


def _project_dir(project_id: str) -> Path:
    path = PROCESSED / project_id

    if not path.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    return path


def _source_video(project_id: str) -> Path:
    matches = list(UPLOADS.glob(f"{project_id}.*"))

    if not matches:
        raise HTTPException(status_code=404, detail="Source video not found")

    return matches[0]


@router.post("/projects/{project_id}/transcribe")
def transcribe_project(project_id: str) -> dict:
    project_dir = _project_dir(project_id)
    audio_path = project_dir / "audio.wav"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Extracted audio not found")

    try:
        raw = transcribe(audio_path)
        transcript = normalize_whisperx(raw)
        retakes = find_retakes(transcript["segments"])

        transcript_path = project_dir / "transcript.json"
        transcript_path.write_text(
            json.dumps(transcript, indent=2),
            encoding="utf-8",
        )

        retake_path = project_dir / "retake_candidates.json"
        retake_path.write_text(
            json.dumps(retakes, indent=2),
            encoding="utf-8",
        )

        return {
            "project_id": project_id,
            "language": transcript.get("language"),
            "segments": len(transcript["segments"]),
            "words": len(transcript["words"]),
            "retake_candidates": len(retakes),
            "transcript": str(transcript_path),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/projects/{project_id}/render")
def render_project(project_id: str) -> dict:
    project_dir = _project_dir(project_id)
    source_video = _source_video(project_id)
    edit_plan_path = project_dir / "edit_plan.json"

    if not edit_plan_path.exists():
        raise HTTPException(status_code=404, detail="Edit plan not found")

    try:
        plan = EditPlan.model_validate_json(
            edit_plan_path.read_text(encoding="utf-8")
        )

        metadata = probe_video(source_video)
        duration = float(metadata["format"]["duration"])

        output_path = EXPORTS / f"{project_id}_clean.mp4"

        render_clean_cut(
            source_video=source_video,
            output_path=output_path,
            duration=duration,
            plan=plan,
        )

        return {
            "project_id": project_id,
            "status": "rendered",
            "output": str(output_path),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
