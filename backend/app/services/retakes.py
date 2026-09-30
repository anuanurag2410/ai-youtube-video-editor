from __future__ import annotations

import re


RESTART_PHRASES = (
    "sorry",
    "let me repeat",
    "let me say that again",
    "let me explain that again",
    "again",
    "wait",
)


def _clean(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text)


def find_retakes(segments: list[dict]) -> list[dict]:
    """
    Find conservative retake candidates.

    This does not automatically remove them. It flags candidates for the
    future AI-director/review layer.
    """
    candidates: list[dict] = []

    for i, segment in enumerate(segments):
        text = _clean(segment.get("text", ""))

        if not text:
            continue

        matched = next(
            (phrase for phrase in RESTART_PHRASES if phrase in text),
            None,
        )

        if matched:
            start_index = max(0, i - 1)
            end_index = min(len(segments) - 1, i + 1)

            candidates.append(
                {
                    "trigger": matched,
                    "start": segments[start_index].get("start"),
                    "end": segments[end_index].get("end"),
                    "segments": segments[start_index : end_index + 1],
                }
            )

    return candidates
