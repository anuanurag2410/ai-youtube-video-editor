from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile

from backend.app.api import router
from backend.app.services.edit_planner import build_initial_plan
from backend.app.services.media import detect_silence, extract_audio, probe_video
from backend.app.services.progress import write_progress


APP_NAME = os.getenv("APP_NAME", "AI YouTube Video Editor")
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "storage"))

UPLOADS = STORAGE_ROOT / "uploads"
PROCESSED = STORAGE_ROOT / "processed"
EXPORTS = STORAGE_ROOT / "exports"

for directory in (UPLOADS, PROCESSED, EXPORTS):
    directory.mkdir(parents=True, exist_ok=True)


app = FastAPI(
    title=APP_NAME,
    version="0.1.0",
    description="AI-assisted long-form YouTube editing backend.",
)

app.include_router(router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME}


@app.post("/projects/upload")
async def upload_project(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix.lower()

    if suffix not in {".mp4", ".mov", ".mkv", ".m4v"}:
        raise HTTPException(
            status_code=400,
            detail="Supported video formats: mp4, mov, mkv, m4v",
        )

    project_id = uuid.uuid4().hex[:12]
    project_dir = PROCESSED / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    video_path = UPLOADS / f"{project_id}{suffix}"

    with video_path.open("wb") as destination:
        shutil.copyfileobj(file.file, destination)

    try:
        write_progress(
            project_dir,
            stage="analyzing_video",
            percent=10,
            message="Analyzing source video",
        )

        metadata = probe_video(video_path)

        write_progress(
            project_dir,
            stage="extracting_audio",
            percent=20,
            message="Extracting audio for speech analysis",
        )

        audio_path = extract_audio(
            video_path,
            project_dir / "audio.wav",
        )
        write_progress(
            project_dir,
            stage="detecting_silence",
            percent=30,
            message="Detecting conversational pauses",
        )

        silences = detect_silence(audio_path)

        write_progress(
            project_dir,
            stage="building_edit_plan",
            percent=38,
            message="Building initial edit decisions",
        )

        edit_plan = build_initial_plan(video_path, silences)
        edit_plan_path = project_dir / "edit_plan.json"
        edit_plan_path.write_text(
            json.dumps(edit_plan.model_dump(), indent=2),
            encoding="utf-8",
        )

        write_progress(
            project_dir,
            stage="ready_for_transcription",
            percent=40,
            message="Initial video analysis complete",
        )

    except Exception as exc:
        write_progress(
            project_dir,
            stage="analysis_failed",
            percent=10,
            message=str(exc),
            state="failed",
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "project_id": project_id,
        "filename": file.filename,
        "video_path": str(video_path),
        "duration": metadata.get("format", {}).get("duration"),
        "silences_detected": len(silences),
        "suggested_cuts": len(edit_plan.cuts),
        "edit_plan": str(edit_plan_path),
        "next_step": "transcription",
    }
