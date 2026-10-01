from __future__ import annotations

from pathlib import Path


def _stamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(transcript: dict, output_path: Path) -> Path:
    lines: list[str] = []
    index = 1

    for segment in transcript.get("segments", []):
        start = segment.get("start")
        end = segment.get("end")
        text = (segment.get("text") or "").strip()

        if start is None or end is None or not text:
            continue

        lines.extend(
            [
                str(index),
                f"{_stamp(float(start))} --> {_stamp(float(end))}",
                text,
                "",
            ]
        )
        index += 1

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
