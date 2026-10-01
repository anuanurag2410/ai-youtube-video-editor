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


def zoompan_expression(plan: EditPlan) -> str | None:
    """
    Create one source-time expression for sparse transcript-driven punch-ins.

    We intentionally keep this binary/subtle instead of aggressive animated
    zooming so educational content stays premium and calm.
    """
    valid = [
        z for z in plan.zooms
        if z.end > z.start and z.scale > 1.0
    ]

    if not valid:
        return None

    expr = "1.0"

    # Later decisions wrap earlier ones. The count is intentionally small.
    for zoom in valid[:24]:
        scale = min(float(zoom.scale), 1.10)
        expr = (
            f"if(between(in_time,{float(zoom.start):.3f},"
            f"{float(zoom.end):.3f}),{scale:.4f},{expr})"
        )

    # Keep syntax predictable for FFmpeg.
    return re.sub(r"\s+", "", expr)
