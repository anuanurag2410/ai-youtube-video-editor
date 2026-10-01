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


def _wrap_words(text: str, max_chars: int = 38, max_lines: int = 2) -> str:
    words = (text or "").strip().split()
    lines: list[str] = []
    current: list[str] = []

    for word in words:
        trial = " ".join(current + [word])
        if current and len(trial) > max_chars:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(" ".join(current))

    return "\n".join(lines[:max_lines])


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


def _caption_card(text: str, path: Path) -> Path:
    text = _wrap_words(text, max_chars=42, max_lines=2)
    if not text:
        text = " "

    font = _font(58, bold=True)
    canvas = Image.new("RGBA", (1500, 220), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8, align="center")
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    card_w = min(1450, text_w + 100)
    card_h = min(205, text_h + 52)
    x0 = (1500 - card_w) // 2
    y0 = (220 - card_h) // 2

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (x0 + 4, y0 + 7, x0 + card_w + 4, y0 + card_h + 7),
        radius=28,
        fill=(0, 0, 0, 150),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(shadow)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (x0, y0, x0 + card_w, y0 + card_h),
        radius=28,
        fill=(10, 13, 18, 218),
        outline=(255, 255, 255, 34),
        width=2,
    )

    tx = 750
    ty = y0 + (card_h - text_h) / 2 - 3
    draw.multiline_text(
        (tx, ty),
        text,
        font=font,
        fill=(255, 255, 255, 255),
        anchor="ma",
        spacing=8,
        align="center",
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)
    return path


def _broll_card(source: Path, slug: str, path: Path) -> Path:
    card = Image.new("RGBA", (820, 500), (0, 0, 0, 0))

    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((25, 30, 795, 480), radius=34, fill=(0, 0, 0, 155))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    card.alpha_composite(shadow)

    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle(
        (18, 18, 802, 468),
        radius=34,
        fill=(248, 249, 252, 245),
        outline=(255, 255, 255, 90),
        width=2,
    )

    try:
        image = Image.open(source).convert("RGBA")
        fitted = ImageOps.contain(image, (700, 350), method=Image.Resampling.LANCZOS)

        if source.stem.lower() == "logo":
            max_logo = ImageOps.contain(fitted, (430, 260), method=Image.Resampling.LANCZOS)
            fitted = max_logo

        ix = (820 - fitted.width) // 2
        iy = 45 + (330 - fitted.height) // 2
        card.alpha_composite(fitted, (ix, iy))
    except Exception:
        pass

    label = _technology_name(slug)
    font = _font(36, bold=True)
    draw.text((410, 415), label, font=font, fill=(24, 29, 39, 255), anchor="mm")

    path.parent.mkdir(parents=True, exist_ok=True)
    card.save(path)
    return path


def _execute(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VisualCompositorError(exc.stderr.strip() or "Visual composition failed") from exc


def _overlay_chain(
    current_label: str,
    input_index: int,
    overlay_index: int,
    start: float,
    end: float,
    width: int,
    x_expr: str,
    y_expr: str,
    fade_duration: float = 0.24,
) -> tuple[list[str], str]:
    duration = max(0.6, end - start)
    fade = min(fade_duration, duration / 3)
    fade_out = max(fade, duration - fade)

    asset_label = f"ov{overlay_index}"
    next_label = f"mix{overlay_index}"

    filters = [
        (
            f"[{input_index}:v]"
            f"scale={width}:-2:force_original_aspect_ratio=decrease,"
            "format=rgba,"
            f"fade=t=in:st=0:d={fade:.3f}:alpha=1,"
            f"fade=t=out:st={fade_out:.3f}:d={fade:.3f}:alpha=1,"
            f"setpts=PTS-STARTPTS+{start:.3f}/TB[{asset_label}]"
        ),
        (
            f"[{current_label}][{asset_label}]"
            f"overlay=x='{x_expr}':y='{y_expr}':"
            f"enable='between(t,{start:.3f},{end:.3f})':"
            f"eof_action=pass:shortest=0[{next_label}]"
        ),
    ]

    return filters, next_label


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

    captions: list[dict] = []
    for index, segment in enumerate(transcript.get("segments", [])):
        start = segment.get("start")
        end = segment.get("end")
        text = (segment.get("text") or "").strip()

        if start is None or end is None or not text:
            continue

        # Avoid cards that flash too quickly.
        start_f = float(start)
        end_f = max(float(end), start_f + 0.85)

        card = _caption_card(
            text,
            generated_dir / f"caption_{index:04d}.png",
        )
        captions.append(
            {
                "path": card,
                "start": start_f,
                "end": end_f,
            }
        )

    resolved_broll = resolve_broll_cues(plan, technology_root)
    broll: list[dict] = []

    for index, cue in enumerate(resolved_broll):
        if not cue["found"]:
            continue

        card = _broll_card(
            cue["path"],
            cue["slug"],
            generated_dir / f"broll_{index:03d}_{cue['slug']}.png",
        )

        broll.append(
            {
                **cue,
                "card": card,
            }
        )

    command = ["ffmpeg", "-y", "-i", str(source_video)]

    overlay_specs: list[dict] = []

    for caption in captions:
        command.extend(["-loop", "1", "-framerate", str(plan.fps), "-i", str(caption["path"])])
        overlay_specs.append({"type": "caption", **caption})

    for cue in broll:
        command.extend(["-loop", "1", "-framerate", str(plan.fps), "-i", str(cue["card"])])
        overlay_specs.append({"type": "broll", **cue})

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

    for idx, spec in enumerate(overlay_specs, start=1):
        if spec["type"] == "caption":
            overlay_filters, current = _overlay_chain(
                current_label=current,
                input_index=idx,
                overlay_index=idx,
                start=float(spec["start"]),
                end=float(spec["end"]),
                width=1350,
                x_expr="(W-w)/2",
                y_expr="H-h-55",
                fade_duration=0.16,
            )
        else:
            overlay_filters, current = _overlay_chain(
                current_label=current,
                input_index=idx,
                overlay_index=idx,
                start=float(spec["start"]),
                end=float(spec["end"]),
                width=690,
                x_expr="W-w-70",
                y_expr="85",
                fade_duration=0.28,
            )

        filter_parts.extend(overlay_filters)

    command.extend(
        [
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            f"[{current}]",
            "-map",
            "0:a?",
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
        "captions_rendered": len(captions),
        "broll_cues_total": len(resolved_broll),
        "broll_assets_found": len(broll),
        "broll_assets_missing": len(resolved_broll) - len(broll),
        "assets_used": [
            {
                "technology": cue["slug"],
                "file": str(cue["path"]),
                "requested_stem": cue["requested_stem"],
            }
            for cue in broll
        ],
    }
