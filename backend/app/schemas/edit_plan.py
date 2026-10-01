from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CutTransition(BaseModel):
    type: Literal["smooth", "hard", "dissolve"] = "smooth"
    duration: float = Field(default=0.09, ge=0.0, le=0.30)
    visual_fix: Literal["none", "punch_in", "punch_out"] = "punch_in"
    scale: float = Field(default=1.04, ge=1.0, le=1.12)


class TimeRange(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reason: str | None = None
    transition: CutTransition = Field(default_factory=CutTransition)


class ZoomDecision(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    scale: float = Field(default=1.06, ge=1.0, le=1.15)


class TextOverlay(BaseModel):
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    text: str
    template: Literal[
        "key_point",
        "chapter",
        "warning",
        "definition",
        "lower_third",
    ] = "key_point"


class BrollDecision(BaseModel):
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    asset_id: str
    kind: Literal["image", "video", "logo", "screenshot", "diagram"]
    motion: Literal["none", "slow_zoom", "pan", "slide_fade"] = "slow_zoom"


class MotionGraphic(BaseModel):
    start: float = Field(ge=0)
    duration: float = Field(gt=0)
    template: Literal["pipeline", "comparison", "steps", "chapter", "key_point"]
    title: str | None = None
    items: list[str] = Field(default_factory=list)


class Chapter(BaseModel):
    start: float = Field(ge=0)
    title: str


class EditPlan(BaseModel):
    version: str = "2.0"
    source_video: str
    output_width: int = 1920
    output_height: int = 1080
    fps: int = 30

    cuts: list[TimeRange] = Field(default_factory=list)
    zooms: list[ZoomDecision] = Field(default_factory=list)
    text_overlays: list[TextOverlay] = Field(default_factory=list)
    broll: list[BrollDecision] = Field(default_factory=list)
    motion_graphics: list[MotionGraphic] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
