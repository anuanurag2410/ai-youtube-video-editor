from __future__ import annotations

import os
from pathlib import Path
from typing import Any


class TranscriptionError(RuntimeError):
    pass


def transcribe(audio_path: Path) -> dict[str, Any]:
    """
    Run WhisperX transcription.

    Import is lazy so the API can boot even before local GPU/model
    dependencies are fully configured.
    """
    try:
        import whisperx
    except ImportError as exc:
        raise TranscriptionError(
            "WhisperX is not installed. Run: pip install -r backend/requirements.txt"
        ) from exc

    device = os.getenv("WHISPER_DEVICE", "cpu")
    compute_type = os.getenv(
        "WHISPER_COMPUTE_TYPE",
        "int8" if device == "cpu" else "float16",
    )
    model_name = os.getenv("WHISPER_MODEL", "large-v3")

    model = whisperx.load_model(
        model_name,
        device=device,
        compute_type=compute_type,
    )

    result = model.transcribe(str(audio_path), batch_size=8)

    language = result.get("language")
    segments = result.get("segments", [])

    if not language:
        return result

    model_a, metadata = whisperx.load_align_model(
        language_code=language,
        device=device,
    )

    return whisperx.align(
        segments,
        model_a,
        metadata,
        str(audio_path),
        device,
        return_char_alignments=False,
    )
