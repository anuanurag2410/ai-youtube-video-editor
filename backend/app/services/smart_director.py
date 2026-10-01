from __future__ import annotations

import re
from collections import Counter

from backend.app.schemas.edit_plan import (
    BrollDecision,
    Chapter,
    CutTransition,
    EditPlan,
    MotionGraphic,
    TextOverlay,
    TimeRange,
    ZoomDecision,
)


TECHNOLOGIES = {
    "databricks": ("databricks", "Databricks"),
    "delta lake": ("delta-lake", "Delta Lake"),
    "apache spark": ("spark", "Apache Spark"),
    "spark": ("spark", "Apache Spark"),
    "pyspark": ("pyspark", "PySpark"),
    "python": ("python", "Python"),
    "sql": ("sql", "SQL"),
    "snowflake": ("snowflake", "Snowflake"),
    "bigquery": ("bigquery", "BigQuery"),
    "airflow": ("airflow", "Apache Airflow"),
    "aws": ("aws", "AWS"),
    "azure": ("azure", "Azure"),
    "gcp": ("gcp", "Google Cloud"),
}

IMPORTANT_PHRASES = (
    "important",
    "remember",
    "interview",
    "common mistake",
    "best practice",
    "key point",
    "difference between",
    "there are",
    "three",
    "four",
    "five",
    "in simple terms",
    "real project",
)

CHAPTER_PHRASES = (
    "now let's",
    "now let us",
    "next let's",
    "next let us",
    "moving on",
    "let's understand",
    "let us understand",
)

HIGH_CONFIDENCE_RETAKES = (
    "sorry",
    "let me repeat",
    "let me say that again",
    "let me explain that again",
    "wait",
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _short_title(text: str, max_words: int = 7) -> str:
    cleaned = _clean(text).strip(" .,:;!?-")
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]) + "…"
    return cleaned


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(p in lower for p in phrases)


def _tech_matches(text: str) -> list[tuple[str, str]]:
    lower = text.lower()
    found: list[tuple[str, str]] = []
    seen: set[str] = set()

    # Longer phrases first prevents "spark" duplicating "apache spark".
    for phrase, payload in sorted(TECHNOLOGIES.items(), key=lambda kv: -len(kv[0])):
        if phrase in lower and payload[0] not in seen:
            found.append(payload)
            seen.add(payload[0])

    return found


def _add_high_confidence_retake_cuts(
    plan: EditPlan,
    segments: list[dict],
) -> int:
    added = 0

    for segment in segments:
        text = _clean(segment.get("text", ""))
        lower = text.lower()
        start = segment.get("start")
        end = segment.get("end")

        if start is None or end is None:
            continue

        words = text.split()
        trigger = next((p for p in HIGH_CONFIDENCE_RETAKES if lower.startswith(p)), None)

        # Only auto-remove tiny explicit restart fragments.
        if not trigger or len(words) > 8 or float(end) - float(start) > 4.0:
            continue

        cut = TimeRange(
            start=max(0.0, float(start) - 0.04),
            end=float(end) + 0.04,
            reason=f"retake:{trigger}",
            transition=CutTransition(
                type="smooth",
                duration=0.08,
                visual_fix="punch_in",
                scale=1.04,
            ),
        )

        # Avoid adding a duplicate/contained cut.
        duplicate = any(
            abs(existing.start - cut.start) < 0.12 and abs(existing.end - cut.end) < 0.12
            for existing in plan.cuts
        )
        if not duplicate:
            plan.cuts.append(cut)
            added += 1

    plan.cuts = sorted(plan.cuts, key=lambda c: (c.start, c.end))
    return added


def enrich_edit_plan(plan: EditPlan, transcript: dict) -> dict:
    segments = [
        s for s in transcript.get("segments", [])
        if s.get("start") is not None and s.get("end") is not None and _clean(s.get("text", ""))
    ]

    plan.version = "3.0"
    plan.zooms = []
    plan.text_overlays = []
    plan.broll = []
    plan.motion_graphics = []
    plan.chapters = []

    tech_counter: Counter[str] = Counter()
    last_zoom_time = -999.0
    last_chapter_time = -999.0

    for segment in segments:
        start = float(segment["start"])
        end = float(segment["end"])
        text = _clean(segment["text"])
        duration = max(0.5, end - start)

        important = _contains_any(text, IMPORTANT_PHRASES)

        if important:
            plan.text_overlays.append(
                TextOverlay(
                    start=start,
                    duration=min(4.5, max(2.5, duration)),
                    text=_short_title(text),
                    template="key_point",
                )
            )

        # Keep zooms sparse: about one every 18s minimum.
        if start - last_zoom_time >= 18.0 and (important or start - last_zoom_time >= 30.0):
            plan.zooms.append(
                ZoomDecision(
                    start=start,
                    end=min(end + 1.5, start + 6.0),
                    scale=1.05,
                )
            )
            last_zoom_time = start

        techs = _tech_matches(text)
        for slug, display in techs[:2]:
            tech_counter[display] += 1
            plan.broll.append(
                BrollDecision(
                    start=start,
                    duration=min(4.0, max(2.5, duration)),
                    asset_id=f"technologies/{slug}/logo.png",
                    kind="logo",
                    motion="slide_fade",
                )
            )

        if (" vs " in f" {text.lower()} " or "difference between" in text.lower()) and techs:
            names = [display for _, display in techs[:2]]
            if len(names) >= 2:
                plan.motion_graphics.append(
                    MotionGraphic(
                        start=start,
                        duration=min(6.0, max(4.0, duration)),
                        template="comparison",
                        title=f"{names[0]} vs {names[1]}",
                        items=names,
                    )
                )

        if start - last_chapter_time >= 75.0 and _contains_any(text, CHAPTER_PHRASES):
            plan.chapters.append(
                Chapter(
                    start=start,
                    title=_short_title(text, max_words=6),
                )
            )
            last_chapter_time = start

    retakes_removed = _add_high_confidence_retake_cuts(plan, segments)

    return {
        "retakes_auto_removed": retakes_removed,
        "smart_zooms": len(plan.zooms),
        "key_point_overlays": len(plan.text_overlays),
        "technology_broll": len(plan.broll),
        "motion_graphics": len(plan.motion_graphics),
        "chapters": len(plan.chapters),
        "technologies": dict(tech_counter.most_common()),
    }
