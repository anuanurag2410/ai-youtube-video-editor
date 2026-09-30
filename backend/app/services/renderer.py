from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.schemas.edit_plan import EditPlan


class RenderError(RuntimeError):
    pass


def _merge_keep_ranges(duration: float, cuts: list) -> list[tuple[float, float]]:
    ordered = sorted(cuts, key=lambda c: c.start)
    keep: list[tuple[float, float]] = []
    cursor = 0.0

    for cut in ordered:
        start = max(0.0, float(cut.start))
        end = min(duration, float(cut.end))

        if start > cursor:
            keep.append((cursor, start))

        cursor = max(cursor, end)

    if cursor < duration:
        keep.append((cursor, duration))

    return [(a, b) for a, b in keep if b - a > 0.05]


def render_clean_cut(
    source_video: Path,
    output_path: Path,
    duration: float,
    plan: EditPlan,
) -> Path:
    keep_ranges = _merge_keep_ranges(duration, plan.cuts)

    if not keep_ranges:
        raise RenderError("No video remains after applying cuts.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    filter_parts: list[str] = []
    concat_inputs: list[str] = []

    for i, (start, end) in enumerate(keep_ranges):
        filter_parts.append(
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
        )
        filter_parts.append(
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        )
        concat_inputs.append(f"[v{i}][a{i}]")

    filter_parts.append(
        "".join(concat_inputs)
        + f"concat=n={len(keep_ranges)}:v=1:a=1[outv][outa]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[outv]",
        "-map",
        "[outa]",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RenderError(exc.stderr.strip() or "Render failed") from exc

    return output_path
