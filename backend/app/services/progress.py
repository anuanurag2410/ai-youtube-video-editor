from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


ProgressState = Literal["queued", "processing", "completed", "failed"]


def write_progress(
    project_dir: Path,
    *,
    stage: str,
    percent: int,
    message: str,
    state: ProgressState = "processing",
) -> dict:
    payload = {
        "state": state,
        "stage": stage,
        "percent": max(0, min(100, int(percent))),
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "status.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return payload


def read_progress(project_dir: Path) -> dict:
    path = project_dir / "status.json"

    if not path.exists():
        return {
            "state": "queued",
            "stage": "waiting",
            "percent": 0,
            "message": "Waiting to start",
        }

    return json.loads(path.read_text(encoding="utf-8"))
