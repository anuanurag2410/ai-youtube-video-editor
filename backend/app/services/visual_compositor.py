from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from backend.app.schemas.edit_plan import EditPlan
from backend.app.services.asset_resolver import resolve_broll_cues
from backend.app.services.premium_graphics import zoompan_expression


class VisualCompositorError(RuntimeError):
    pass


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]

    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def _technology_name(slug: str) -> str:
    mapping = {
        "databricks": "Databricks",
        "spark": "Apache Spark",
        "pyspark": "PySpark",
        "delta-lake": "Delta Lake",
        "python": "Python",
        "pandas": "Pandas",
        "sql": "SQL",
        "kafka": "Apache Kafka",
        "airflow": "Apache Airflow",
        "dbt": "dbt",
        "snowflake": "Snowflake",
        "bigquery": "BigQuery",
        "redshift": "Amazon Redshift",
        "synapse": "Azure Synapse",
        "s3": "Amazon S3",
        "adls": "Azure Data Lake Storage",
        "gcs": "Google Cloud Storage",
        "adf": "Azure Data Factory",
        "aws-glue": "AWS Glue",
        "unity-catalog": "Unity Catalog",
        "iceberg": "Apache Iceberg",
        "hudi": "Apache Hudi",
        "flink": "Apache Flink",
        "hadoop": "Apache Hadoop",
        "hive": "Apache Hive",
        "hdfs": "HDFS",
        "teradata": "Teradata",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "git": "Git",
        "github": "GitHub",
        "jenkins": "Jenkins",
        "terraform": "Terraform",
        "aws": "AWS",
        "azure": "Microsoft Azure",
        "gcp": "Google Cloud",
        "mlflow": "MLflow",
        "powerbi": "Power BI",
    }
    return mapping.get(slug, slug.replace("-", " ").title())


def _asset_kind(source: Path) -> str:
    stem = source.stem.lower()
    if stem == "logo" or "logo" in stem:
        return "logo"
    if stem in {"ui", "screenshot"} or "screen" in stem:
        return "ui"
    if stem == "diagram" or "arch" in stem or "diagram" in stem:
        return "diagram"
    return "broll"


def _make_glass_card(source: Path, slug: str, path: Path) -> tuple[Path, str]:
    kind = _asset_kind(source)
    is_logo = kind == "logo"

    if is_logo:
        canvas_size = (720, 420)
        image_box = (500, 250)
        label_y = 345
        radius = 34
    else:
        canvas_size = (1120, 690)
        image_box = (1000, 535)
        label_y = 615
        radius = 38

    card = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    w, h = canvas_size

    shadow = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (34, 38, w - 18, h - 16),
        radius=radius,
        fill=(0, 0, 0, 155),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    card.alpha_composite(shadow)

    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (20, 20, w - 28, h - 28),
        radius=radius,
        fill=(247, 249, 252, 246),
        outline=(255, 255, 255, 155),
        width=3,
    )

    # A faint top highlight gives the card a glass/premium feel.
    draw.rounded_rectangle(
        (28, 28, w - 36, 72),
        radius=20,
        fill=(255, 255, 255, 55),
    )

    try:
        image = Image.open(source).convert("RGBA")

        if is_logo:
            fitted = ImageOps.contain(
                image,
                image_box,
                method=Image.Resampling.LANCZOS,
            )
        else:
            # Screenshots/diagrams get a larger presentation and a soft inner frame.
            preview_bg = Image.new("RGBA", (1020, 555), (236, 239, 245, 255))
            preview_draw = ImageDraw.Draw(preview_bg)
            preview_draw.rounded_rectangle(
                (0, 0, 1019, 554),
                radius=24,
                fill=(236, 239, 245, 255),
                outline=(215, 220, 230, 255),
                width=2,
            )
            fitted = ImageOps.contain(
                image,
                image_box,
                method=Image.Resampling.LANCZOS,
            )
            px = (1020 - fitted.width) // 2
            py = (555 - fitted.height) // 2
            preview_bg.alpha_composite(fitted, (px, py))
            fitted = preview_bg

        ix = (w - fitted.width) // 2
        if is_logo:
            iy = 55 + (245 - fitted.height) // 2
        else:
            iy = 45

        card.alpha_composite(fitted, (ix, iy))
    except Exception:
        pass

    label = _technology_name(slug)
    font = _font(36 if is_logo else 34, bold=True)
    draw = ImageDraw.Draw(card)
    draw.text(
        (w // 2, label_y),
        label,
        font=font,
        fill=(24, 29, 39, 255),
        anchor="mm",
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    card.save(path)
    return path, kind


def _execute(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VisualCompositorError(exc.stderr.strip() or "Visual composition failed") from exc


def _premium_overlay_chain(
    current_label: str,
    input_index: int,
    overlay_index: int,
    start: float,
    end: float,
    kind: str,
    fps: int,
) -> tuple[list[str], str]:
    duration = max(1.4, end - start)
    fade = min(0.28, duration / 4)
    fade_out_start = max(fade, duration - fade)

    if kind == "logo":
        width = 560
        height = 327
        target_x = "W-w-72"
        target_y = "92"
        zoom_limit = 1.035
        zoom_step = 0.00045
        slide_px = 300
    else:
        width = 900
        height = 554
        target_x = "W-w-60"
        target_y = "(H-h)/2-10"
        zoom_limit = 1.045
        zoom_step = 0.00035
        slide_px = 420

    asset_label = f"ov{overlay_index}"
    next_label = f"mix{overlay_index}"

    # Small Ken Burns movement on the card itself.
    card_filter = (
        f"[{input_index}:v]"
        f"scale={width}:-2:force_original_aspect_ratio=decrease,"
        "format=rgba,"
        f"zoompan=z='min(zoom+{zoom_step:.6f},{zoom_limit:.4f})':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d=1:s={width}x{height}:fps={fps},"
        f"fade=t=in:st=0:d={fade:.3f}:alpha=1,"
        f"fade=t=out:st={fade_out_start:.3f}:d={fade:.3f}:alpha=1,"
        f"setpts=PTS-STARTPTS+{start:.3f}/TB[{asset_label}]"
    )

    # Slide from the right for ~0.35s and then add a tiny floating drift.
    x_expr = (
        f"({target_x})+"
        f"max(0,({start + 0.35:.3f}-t)*{slide_px / 0.35:.3f})+"
        f"8*sin((t-{start:.3f})*1.15)"
    )
    y_expr = f"({target_y})+4*sin((t-{start:.3f})*0.85)"

    overlay_filter = (
        f"[{current_label}][{asset_label}]"
        f"overlay=x='{x_expr}':y='{y_expr}':"
        f"enable='between(t,{start:.3f},{end:.3f})':"
        f"eof_action=pass:shortest=0[{next_label}]"
    )

    return [card_filter, overlay_filter], next_label


def render_visual_master(
    source_video: Path,
    output_path: Path,
    plan: EditPlan,
    transcript: dict[str, Any],
    project_dir: Path,
    technology_root: Path = Path("assets/technologies"),
) -> dict:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    generated_dir = project_dir / "generated_visuals"
    generated_dir.mkdir(parents=True, exist_ok=True)

    # Captions are intentionally excluded here. The user adds them later in Premiere Pro.
    resolved_broll = resolve_broll_cues(plan, technology_root)
    broll: list[dict] = []

    for index, cue in enumerate(resolved_broll):
        if not cue["found"]:
            continue

        card, kind = _make_glass_card(
            cue["path"],
            cue["slug"],
            generated_dir / f"broll_{index:03d}_{cue['slug']}.png",
        )

        broll.append(
            {
                **cue,
                "card": card,
                "kind": kind,
            }
        )

    command = ["ffmpeg", "-y", "-i", str(source_video)]

    for cue in broll:
        command.extend(
            [
                "-loop",
                "1",
                "-framerate",
                str(plan.fps),
                "-i",
                str(cue["card"]),
            ]
        )

    base_filters = [
        f"scale={plan.output_width}:{plan.output_height}:force_original_aspect_ratio=decrease",
        f"pad={plan.output_width}:{plan.output_height}:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
        f"fps={plan.fps}",
    ]

    zoom_expr = zoompan_expression(plan, fps=plan.fps)
    if zoom_expr:
        base_filters.append(
            "zoompan="
            f"z='{zoom_expr}':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            f"d=1:s={plan.output_width}x{plan.output_height}:fps={plan.fps}"
        )

    filter_parts = [
        f"[0:v]{','.join(base_filters)},format=yuv420p[base0]"
    ]

    current = "base0"

    for idx, cue in enumerate(broll, start=1):
        overlay_filters, current = _premium_overlay_chain(
            current_label=current,
            input_index=idx,
            overlay_index=idx,
            start=float(cue["start"]),
            end=float(cue["end"]),
            kind=cue["kind"],
            fps=plan.fps,
        )
        filter_parts.extend(overlay_filters)

    if broll:
        command.extend(
            [
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                f"[{current}]",
                "-map",
                "0:a?",
            ]
        )
    else:
        # Still apply smart zooms even if there are no local B-roll assets.
        command.extend(
            [
                "-vf",
                ",".join(base_filters),
                "-map",
                "0:v",
                "-map",
                "0:a?",
            ]
        )

    command.extend(
        [
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
            "-shortest",
            str(output_path),
        ]
    )

    _execute(command)

    return {
        "output": str(output_path),
        "captions_rendered": 0,
        "broll_cues_total": len(resolved_broll),
        "broll_assets_found": len(broll),
        "broll_assets_missing": len(resolved_broll) - len(broll),
        "assets_used": [
            {
                "technology": cue["slug"],
                "file": str(cue["path"]),
                "requested_stem": cue["requested_stem"],
                "kind": cue["kind"],
            }
            for cue in broll
        ],
    }
