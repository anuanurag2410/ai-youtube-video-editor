from __future__ import annotations

from typing import Any


def normalize_whisperx(result: dict[str, Any]) -> dict:
    segments_out: list[dict] = []
    words_out: list[dict] = []

    for segment in result.get("segments", []):
        segment_item = {
            "start": segment.get("start"),
            "end": segment.get("end"),
            "text": (segment.get("text") or "").strip(),
        }
        segments_out.append(segment_item)

        for word in segment.get("words", []) or []:
            if word.get("start") is None or word.get("end") is None:
                continue

            words_out.append(
                {
                    "word": (word.get("word") or "").strip(),
                    "start": word.get("start"),
                    "end": word.get("end"),
                    "score": word.get("score"),
                }
            )

    return {
        "language": result.get("language"),
        "segments": segments_out,
        "words": words_out,
    }
