from __future__ import annotations

from pathlib import Path

from backend.app.schemas.edit_plan import CutTransition, EditPlan, TimeRange


def silence_to_cuts(
    silences: list[dict],
    keep_pause: float = 0.20,
    remove_threshold: float = 0.75,
) -> list[TimeRange]:
    """
    Shorten conversational pauses for a tighter YouTube pace while retaining
    a small amount of natural breathing room.

    V2.1 uses a more practical talking-head profile:
    - detect shorter pauses upstream (~0.55s)
    - shorten pauses from ~0.75s onward
    - retain ~0.20s total pause around each cut

    It also attaches a subtle transition policy to every generated cut:
    - ~90ms visual/audio blend
    - subtle post-cut punch-in
    """
    cuts: list[TimeRange] = []

    for silence in silences:
        duration = float(silence["duration"])

        if duration < remove_threshold:
            continue

        start = float(silence["start"]) + keep_pause / 2
        end = float(silence["end"]) - keep_pause / 2

        if end > start:
            cuts.append(
                TimeRange(
                    start=start,
                    end=end,
                    reason="long_silence",
                    transition=CutTransition(
                        type="smooth",
                        duration=0.09,
                        visual_fix="punch_in",
                        scale=1.04,
                    ),
                )
            )

    return cuts


def build_initial_plan(
    source_video: Path,
    silences: list[dict],
) -> EditPlan:
    return EditPlan(
        source_video=str(source_video),
        cuts=silence_to_cuts(silences),
    )
