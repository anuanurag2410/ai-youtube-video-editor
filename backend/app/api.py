from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.app.schemas.edit_plan import EditPlan
from backend.app.services.media import probe_video
from backend.app.services.progress import read_progress, write_progress
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


@router.get("/projects/{project_id}/status")
def project_status(project_id: str) -> dict:
    project_dir = _project_dir(project_id)
    return {
        "project_id": project_id,
        **read_progress(project_dir),
    }


@router.post("/projects/{project_id}/transcribe")
def transcribe_project(project_id: str) -> dict:
    project_dir = _project_dir(project_id)
    audio_path = project_dir / "audio.wav"

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Extracted audio not found")

    try:
        write_progress(
            project_dir,
            stage="transcription",
            percent=45,
            message="Loading speech model and transcribing audio",
        )

        raw = transcribe(audio_path)

        write_progress(
            project_dir,
            stage="alignment",
            percent=68,
            message="Aligning words with precise timestamps",
        )

        transcript = normalize_whisperx(raw)

        write_progress(
            project_dir,
            stage="retake_analysis",
            percent=78,
            message="Checking transcript for retake candidates",
        )

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

        write_progress(
            project_dir,
            stage="transcription_complete",
            percent=82,
            message="Transcript analysis complete",
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
        write_progress(
            project_dir,
            stage="transcription_failed",
            percent=45,
            message=str(exc),
            state="failed",
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/projects/{project_id}/render")
def render_project(project_id: str) -> dict:
    project_dir = _project_dir(project_id)
    source_video = _source_video(project_id)
    edit_plan_path = project_dir / "edit_plan.json"

    if not edit_plan_path.exists():
        raise HTTPException(status_code=404, detail="Edit plan not found")

    try:
        write_progress(
            project_dir,
            stage="preparing_render",
            percent=84,
            message="Preparing premium cut render",
        )

        plan = EditPlan.model_validate_json(
            edit_plan_path.read_text(encoding="utf-8")
        )

        metadata = probe_video(source_video)
        duration = float(metadata["format"]["duration"])

        output_path = EXPORTS / f"{project_id}_clean.mp4"

        write_progress(
            project_dir,
            stage="rendering",
            percent=90,
            message="Rendering smooth cuts and transitions",
        )

        render_clean_cut(
            source_video=source_video,
            output_path=output_path,
            duration=duration,
            plan=plan,
        )

        write_progress(
            project_dir,
            stage="complete",
            percent=100,
            message="Video render complete",
            state="completed",
        )

        return {
            "project_id": project_id,
            "status": "rendered",
            "output": str(output_path),
        }

    except Exception as exc:
        write_progress(
            project_dir,
            stage="render_failed",
            percent=90,
            message=str(exc),
            state="failed",
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
