from __future__ import annotations

import re
from pathlib import Path

from backend.app.schemas.edit_plan import EditPlan


def _ass_time(seconds: float) -> str:
    centis = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    text = (text or "").replace("\\", r"\\")
    text = text.replace("{", r"\{").replace("}", r"\}")
    text = text.replace("\n", r"\N")
    return text.strip()


def _wrap_caption(text: str, max_chars: int = 42) -> str:
    words = text.split()
    if not words:
        return ""

    lines: list[str] = []
    current: list[str] = []
    length = 0

    for word in words:
        extra = len(word) + (1 if current else 0)
        if current and length + extra > max_chars:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += extra

    if current:
        lines.append(" ".join(current))

    return r"\N".join(lines[:2])


def write_premium_ass(
    transcript: dict,
    plan: EditPlan,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,54,&H00FFFFFF,&H000000FF,&H90000000,&H70000000,-1,0,0,0,100,100,0,0,1,3,1,2,120,120,66,1
Style: KeyPoint,Arial,66,&H00FFFFFF,&H000000FF,&H90000000,&H80000000,-1,0,0,0,100,100,0,0,3,2,0,8,160,160,100,1
Style: Chapter,Arial,72,&H00FFFFFF,&H000000FF,&H90000000,&H90000000,-1,0,0,0,100,100,0,0,3,2,0,5,180,180,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []

    # Main educational captions.
    for segment in transcript.get("segments", []):
        start = segment.get("start")
        end = segment.get("end")
        text = (segment.get("text") or "").strip()

        if start is None or end is None or not text:
            continue

        wrapped = _wrap_caption(_escape_ass(text))
        if wrapped:
            events.append(
                f"Dialogue: 0,{_ass_time(float(start))},{_ass_time(float(end))},"
                f"Caption,,0,0,0,,{wrapped}"
            )

    # Important transcript moments.
    for overlay in plan.text_overlays:
        start = float(overlay.start)
        end = start + float(overlay.duration)
        text = _escape_ass(overlay.text)

        if not text:
            continue

        events.append(
            f"Dialogue: 2,{_ass_time(start)},{_ass_time(end)},"
            f"KeyPoint,,0,0,0,,{{\\fad(180,180)}}{text}"
        )

    # Chapter resets.
    for chapter in plan.chapters:
        start = float(chapter.start)
        end = start + 3.2
        text = _escape_ass(chapter.title)

        events.append(
            f"Dialogue: 3,{_ass_time(start)},{_ass_time(end)},"
            f"Chapter,,0,0,0,,{{\\fad(220,250)}}{text}"
        )

    output_path.write_text(
        header + "\n".join(events) + "\n",
        encoding="utf-8",
    )
    return output_path


def zoompan_expression(plan: EditPlan, fps: int = 30) -> str | None:
    """
    Create a smooth source-time zoom expression.

    Each zoom eases in and back out using a sine curve, so there is no sudden
    1.0 -> 1.05 jump.
    """
    valid = [
        z for z in plan.zooms
        if z.end > z.start and z.scale > 1.0
    ]

    if not valid:
        return None

    expr = "1.0"

    for zoom in valid[:24]:
        start_frame = float(zoom.start) * fps
        end_frame = float(zoom.end) * fps
        span = max(1.0, end_frame - start_frame)
        amount = min(float(zoom.scale), 1.10) - 1.0

        smooth = (
            f"1+{amount:.5f}*sin(PI*(on-{start_frame:.3f})/{span:.3f})"
        )

        expr = (
            f"if(between(on,{start_frame:.3f},{end_frame:.3f}),"
            f"{smooth},{expr})"
        )

    return re.sub(r"\s+", "", expr)


def _ffmpeg_text(text: str) -> str:
    text = (text or "").replace("\\", r"\\")
    text = text.replace(":", r"\:")
    text = text.replace("'", r"\'")
    text = text.replace("%", r"\%")
    text = text.replace(",", r"\,")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _caption_text(text: str, max_words: int = 10) -> str:
    words = re.sub(r"\s+", " ", (text or "").strip()).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + "…"


def _technology_name(asset_id: str) -> str:
    slug = Path(asset_id).parts[-2] if len(Path(asset_id).parts) >= 2 else asset_id
    names = {
        "databricks": "Databricks",
        "spark": "Apache Spark",
        "pyspark": "PySpark",
        "python": "Python",
        "sql": "SQL",
        "snowflake": "Snowflake",
        "bigquery": "BigQuery",
        "airflow": "Apache Airflow",
        "aws": "AWS",
        "azure": "Azure",
        "gcp": "Google Cloud",
        "delta-lake": "Delta Lake",
    }
    return names.get(slug, slug.replace("-", " ").title())


def build_drawtext_filters(transcript: dict, plan: EditPlan) -> list[str]:
    """
    Build source-time caption and technology-card filters.

    Uses drawtext/drawbox only, avoiding libass/subtitles dependencies.
    """
    filters: list[str] = []

    for segment in transcript.get("segments", []):
        start = segment.get("start")
        end = segment.get("end")
        text = _caption_text(segment.get("text", ""))

        if start is None or end is None or not text:
            continue

        safe = _ffmpeg_text(text)
        filters.append(
            "drawtext="
            "font='Arial':"
            f"text='{safe}':"
            "fontsize=54:"
            "fontcolor=white:"
            "borderw=2:"
            "bordercolor=black@0.75:"
            "box=1:"
            "boxcolor=black@0.55:"
            "boxborderw=20:"
            "x=(w-text_w)/2:"
            "y=h-text_h-92:"
            f"enable='between(t,{float(start):.3f},{float(end):.3f})'"
        )

    # Key points appear top-left and are intentionally sparse.
    for overlay in plan.text_overlays[:12]:
        safe = _ffmpeg_text(_caption_text(overlay.text, max_words=7))
        start = float(overlay.start)
        end = start + float(overlay.duration)

        filters.append(
            "drawtext="
            "font='Arial':"
            f"text='{safe}':"
            "fontsize=46:"
            "fontcolor=white:"
            "box=1:"
            "boxcolor=black@0.68:"
            "boxborderw=22:"
            "x=70:"
            "y=70:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )

    # Technology cards provide immediate visual context until real logo assets
    # are supplied in assets/technologies/<slug>/logo.png.
    for cue in plan.broll[:20]:
        start = float(cue.start)
        end = start + float(cue.duration)
        name = _ffmpeg_text(_technology_name(cue.asset_id))

        filters.append(
            "drawbox="
            "x=w-470:y=75:w=390:h=125:"
            "color=black@0.64:t=fill:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )
        filters.append(
            "drawtext="
            "font='Arial':"
            f"text='{name}':"
            "fontsize=42:"
            "fontcolor=white:"
            "x=w-text_w-115:"
            "y=112:"
            f"enable='between(t,{start:.3f},{end:.3f})'"
        )

    return filters
