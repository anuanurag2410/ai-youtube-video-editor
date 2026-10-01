from __future__ import annotations

import json
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        raise MediaError(exc.stderr.strip() or "Media command failed") from exc


def probe_video(path: Path) -> dict:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
    )
    return json.loads(result.stdout)


def extract_audio(video_path: Path, audio_path: Path) -> Path:
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
    )

    return audio_path


def detect_silence(
    audio_path: Path,
    noise_db: int = -40,
    minimum_duration: float = 0.55,
) -> list[dict]:
    command = [
        "ffmpeg",
        "-i",
        str(audio_path),
        "-af",
        f"silencedetect=noise={noise_db}dB:d={minimum_duration}",
        "-f",
        "null",
        "-",
    ]

    result = subprocess.run(command, capture_output=True, text=True)
    stderr = result.stderr

    starts: list[float] = []
    silences: list[dict] = []

    for line in stderr.splitlines():
        if "silence_start:" in line:
            starts.append(float(line.split("silence_start:")[1].strip()))

        elif "silence_end:" in line and starts:
            tail = line.split("silence_end:")[1].strip()
            end_text = tail.split("|")[0].strip()
            end = float(end_text)
            start = starts.pop(0)

            silences.append(
                {
                    "start": start,
                    "end": end,
                    "duration": end - start,
                }
            )

    return silences
