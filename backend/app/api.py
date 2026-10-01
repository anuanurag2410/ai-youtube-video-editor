from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.app.schemas.edit_plan import CutTransition, EditPlan, TimeRange
from backend.app.services.media import probe_video
from backend.app.services.progress import read_progress, write_progress
from backend.app.services.premium_graphics import write_premium_ass
from backend.app.services.captions import write_srt
from backend.app.services.smart_director import enrich_edit_plan
from backend.app.services.renderer import render_clean_cut
from backend.app.services.retakes import find_retakes
from backend.app.services.transcript_utils import normalize_whisperx
from backend.app.services.transcription import transcribe
from backend.app.services.visual_compositor import render_visual_master


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


def _add_speech_boundary_cuts(
    project_dir: Path,
    project_id: str,
    transcript: dict,
    pre_roll: float = 0.25,
    post_roll: float = 0.35,
    minimum_dead_air: float = 0.60,
) -> dict:
    """Trim non-speaking lead-in/tail using transcript timing, not raw volume."""
    segments = [
        s for s in transcript.get("segments", [])
        if s.get("start") is not None and s.get("end") is not None and (s.get("text") or "").strip()
    ]

    if not segments:
        return {"leading_trim": 0.0, "trailing_trim": 0.0}

    edit_plan_path = project_dir / "edit_plan.json"
    if not edit_plan_path.exists():
        return {"leading_trim": 0.0, "trailing_trim": 0.0}

    plan = EditPlan.model_validate_json(edit_plan_path.read_text(encoding="utf-8"))
    source_video = _source_video(project_id)
    metadata = probe_video(source_video)
    duration = float(metadata["format"]["duration"])

    first_speech = float(segments[0]["start"])
    last_speech = float(segments[-1]["end"])

    leading_end = max(0.0, first_speech - pre_roll)
    trailing_start = min(duration, last_speech + post_roll)

    added = []

    if leading_end >= minimum_dead_air:
        added.append(
            TimeRange(
                start=0.0,
                end=leading_end,
                reason="leading_dead_air",
                transition=CutTransition(
                    type="hard",
                    duration=0.0,
                    visual_fix="none",
                    scale=1.0,
                ),
            )
        )

    if duration - trailing_start >= minimum_dead_air:
        added.append(
            TimeRange(
                start=trailing_start,
                end=duration,
                reason="trailing_dead_air",
                transition=CutTransition(
                    type="hard",
                    duration=0.0,
                    visual_fix="none",
                    scale=1.0,
                ),
            )
        )

    if added:
        existing = list(plan.cuts)
        existing.extend(added)
        plan.cuts = sorted(existing, key=lambda x: (x.start, x.end))
        edit_plan_path.write_text(
            json.dumps(plan.model_dump(), indent=2),
            encoding="utf-8",
        )

    return {
        "leading_trim": leading_end if leading_end >= minimum_dead_air else 0.0,
        "trailing_trim": (duration - trailing_start) if duration - trailing_start >= minimum_dead_air else 0.0,
    }


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
        boundary_trims = _add_speech_boundary_cuts(project_dir, project_id, transcript)

        edit_plan_path = project_dir / "edit_plan.json"
        plan = EditPlan.model_validate_json(
            edit_plan_path.read_text(encoding="utf-8")
        )
        smart_summary = enrich_edit_plan(plan, transcript)
        edit_plan_path.write_text(
            json.dumps(plan.model_dump(), indent=2),
            encoding="utf-8",
        )

        captions_path = write_srt(
            transcript,
            project_dir / "captions_raw.srt",
        )

        summary_path = project_dir / "edit_summary.json"
        summary_path.write_text(
            json.dumps(smart_summary, indent=2),
            encoding="utf-8",
        )

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
            "leading_dead_air_trimmed": boundary_trims["leading_trim"],
            "trailing_dead_air_trimmed": boundary_trims["trailing_trim"],
            "smart_edit_summary": smart_summary,
            "captions": str(captions_path),
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

        output_path = EXPORTS / f"{project_id}_premium.mp4"

        transcript_path = project_dir / "transcript.json"
        ass_path = None
        if transcript_path.exists():
            transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
            ass_path = write_premium_ass(
                transcript,
                plan,
                project_dir / "premium_overlay.ass",
                width=plan.output_width,
                height=plan.output_height,
            )

        visual_stats = {
            "captions_rendered": 0,
            "broll_cues_total": 0,
            "broll_assets_found": 0,
            "broll_assets_missing": 0,
            "assets_used": [],
        }

        render_source = source_video
        render_duration = duration

        if transcript_path.exists():
            write_progress(
                project_dir,
                stage="visual_compositing",
                percent=87,
                message="Adding captions and technology B-roll",
            )

            visual_master = project_dir / "visual_master.mp4"
            visual_stats = render_visual_master(
                source_video=source_video,
                output_path=visual_master,
                plan=plan,
                transcript=transcript,
                project_dir=project_dir,
            )

            render_source = visual_master
            visual_metadata = probe_video(visual_master)
            render_duration = float(visual_metadata["format"]["duration"])

        write_progress(
            project_dir,
            stage="rendering",
            percent=94,
            message="Applying clean cuts and smooth transitions",
        )

        clean_plan = plan.model_copy(deep=True)
        clean_plan.zooms = []
        clean_plan.text_overlays = []
        clean_plan.broll = []
        clean_plan.motion_graphics = []
        clean_plan.chapters = []

        render_clean_cut(
            source_video=render_source,
            output_path=output_path,
            duration=render_duration,
            plan=clean_plan,
            ass_path=None,
            transcript=None,
        )

        write_progress(
            project_dir,
            stage="complete",
            percent=100,
            message="Premium video render complete",
            state="completed",
        )

        return {
            "project_id": project_id,
            "status": "rendered",
            "output": str(output_path),
            "visuals": visual_stats,
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
