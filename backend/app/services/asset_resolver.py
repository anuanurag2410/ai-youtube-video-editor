from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from backend.app.schemas.edit_plan import EditPlan


SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"
}

PREFERRED_STEMS = ("logo", "ui", "diagram", "broll")


def _slug_from_asset_id(asset_id: str) -> str:
    parts = Path(asset_id).parts
    if len(parts) >= 2:
        return parts[-2]
    return Path(asset_id).stem


def _images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []

    return sorted(
        [
            p for p in folder.iterdir()
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ],
        key=lambda p: p.name.lower(),
    )


def find_asset_by_stem(folder: Path, stem: str) -> Path | None:
    wanted = stem.lower().strip()

    for path in _images(folder):
        if path.stem.lower() == wanted:
            return path

    return None


def resolve_asset(
    technology_root: Path,
    slug: str,
    preferred_stem: str,
) -> Path | None:
    """
    Resolve assets by filename stem, ignoring extension.

    For example all of these satisfy preferred_stem='logo':
      logo.png
      logo.jpg
      logo.jpeg
      logo.webp
    """
    folder = technology_root / slug

    direct = find_asset_by_stem(folder, preferred_stem)
    if direct:
        return direct

    for fallback in PREFERRED_STEMS:
        candidate = find_asset_by_stem(folder, fallback)
        if candidate:
            return candidate

    # Final fallback: any supported image in the technology folder.
    available = _images(folder)
    return available[0] if available else None


def resolve_broll_cues(
    plan: EditPlan,
    technology_root: Path,
) -> list[dict]:
    """
    Resolve each technology cue to an actual local image.

    Repeated mentions rotate through logo -> ui -> diagram -> broll when those
    files exist, giving videos more visual variety.
    """
    occurrences: dict[str, int] = defaultdict(int)
    resolved: list[dict] = []

    for cue in plan.broll:
        slug = _slug_from_asset_id(cue.asset_id)
        occurrence = occurrences[slug]
        occurrences[slug] += 1

        preferred = PREFERRED_STEMS[occurrence % len(PREFERRED_STEMS)]
        asset = resolve_asset(technology_root, slug, preferred)

        resolved.append(
            {
                "slug": slug,
                "start": float(cue.start),
                "duration": float(cue.duration),
                "end": float(cue.start + cue.duration),
                "requested_stem": preferred,
                "path": asset,
                "found": asset is not None,
            }
        )

    return resolved
