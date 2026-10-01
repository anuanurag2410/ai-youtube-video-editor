from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.app.schemas.edit_plan import EditPlan, TimeRange


class RenderError(RuntimeError):
    pass


@dataclass
class KeepSegment:
    start: float
    end: float
    incoming_cut: TimeRange | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


def _build_keep_segments(duration: float, cuts: list[TimeRange]) -> list[KeepSegment]:
    ordered = sorted(cuts, key=lambda c: c.start)
    keep: list[KeepSegment] = []
    cursor = 0.0
    incoming: TimeRange | None = None

    for cut in ordered:
        start = max(0.0, float(cut.start))
        end = min(duration, float(cut.end))

        if start > cursor:
            keep.append(
                KeepSegment(
                    start=cursor,
                    end=start,
                    incoming_cut=incoming,
                )
            )

        cursor = max(cursor, end)
        incoming = cut

    if cursor < duration:
        keep.append(
            KeepSegment(
                start=cursor,
                end=duration,
                incoming_cut=incoming,
            )
        )

    return [segment for segment in keep if segment.duration > 0.08]


def _safe_transition_duration(
    requested: float,
    left_duration: float,
    right_duration: float,
) -> float:
    # Keep transition well below either neighboring shot duration.
    maximum = min(0.30, left_duration * 0.25, right_duration * 0.25)
    return max(0.0, min(requested, maximum))


def _video_filter_for_segment(
    index: int,
    segment: KeepSegment,
    fps: int,
    output_width: int,
    output_height: int,
) -> str:
    base = (
        f"[0:v]trim=start={segment.start}:end={segment.end},"
        f"setpts=PTS-STARTPTS,fps={fps},settb=AVTB,setsar=1"
    )

    incoming = segment.incoming_cut
    if (
        incoming
        and incoming.transition.visual_fix == "punch_in"
        and incoming.transition.scale > 1.0
    ):
        scale = incoming.transition.scale

        # Create a subtle center punch-in. Rounding during scale/crop can
        # produce dimensions a few pixels smaller than the source, so every
        # segment is normalized to the exact output dimensions afterwards.
        base += (
            f",scale=ceil(iw*{scale}/2)*2:ceil(ih*{scale}/2)*2,"
            f"crop=trunc(iw/{scale}/2)*2:trunc(ih/{scale}/2)*2"
        )

    # xfade requires both inputs to have identical dimensions, pixel format,
    # SAR, frame rate and time base. Normalize every segment here.
    base += (
        f",scale={output_width}:{output_height}:flags=lanczos,"
        f"setsar=1,format=yuv420p"
    )

    return base + f"[v{index}]"


def _audio_filter_for_segment(index: int, segment: KeepSegment) -> str:
    return (
        f"[0:a]atrim=start={segment.start}:end={segment.end},"
        f"asetpts=PTS-STARTPTS[a{index}]"
    )


def render_clean_cut(
    source_video: Path,
    output_path: Path,
    duration: float,
    plan: EditPlan,
) -> Path:
    segments = _build_keep_segments(duration, plan.cuts)

    if not segments:
        raise RenderError("No video remains after applying cuts.")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # No cuts: pass through a normalized encode.
    if len(segments) == 1:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source_video),
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
        _execute(command)
        return output_path

    filter_parts: list[str] = []

    for i, segment in enumerate(segments):
        filter_parts.append(
            _video_filter_for_segment(
                i,
                segment,
                plan.fps,
                plan.output_width,
                plan.output_height,
            )
        )
        filter_parts.append(_audio_filter_for_segment(i, segment))

    video_label = "v0"
    audio_label = "a0"
    composed_duration = segments[0].duration

    for i in range(1, len(segments)):
        cut = segments[i].incoming_cut
        requested = cut.transition.duration if cut else 0.09
        transition_type = cut.transition.type if cut else "smooth"

        if transition_type == "hard":
            transition_duration = 0.0
        else:
            transition_duration = _safe_transition_duration(
                requested=requested,
                left_duration=composed_duration,
                right_duration=segments[i].duration,
            )

        next_video = f"vx{i}"
        next_audio = f"ax{i}"

        if transition_duration <= 0.001:
            filter_parts.append(
                f"[{video_label}][v{i}]concat=n=2:v=1:a=0[{next_video}]"
            )
            filter_parts.append(
                f"[{audio_label}][a{i}]concat=n=2:v=0:a=1[{next_audio}]"
            )
            composed_duration += segments[i].duration
        else:
            # The tiny xfade prevents a single-frame visual snap.
            # Audio uses an equal-duration acrossfade to avoid clicks/pops.
            offset = max(0.0, composed_duration - transition_duration)
            filter_parts.append(
                f"[{video_label}][v{i}]"
                f"xfade=transition=fade:duration={transition_duration}:offset={offset}"
                f"[{next_video}]"
            )
            filter_parts.append(
                f"[{audio_label}][a{i}]"
                f"acrossfade=d={transition_duration}:c1=tri:c2=tri"
                f"[{next_audio}]"
            )
            composed_duration += segments[i].duration - transition_duration

        video_label = next_video
        audio_label = next_audio

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source_video),
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        f"[{video_label}]",
        "-map",
        f"[{audio_label}]",
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

    _execute(command)
    return output_path


def _execute(command: list[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RenderError(exc.stderr.strip() or "Render failed") from exc
