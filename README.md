# AI YouTube Video Editor

Private-first AI-assisted long-form YouTube editing pipeline.

## Goal

Turn a raw talking-head / educational recording into a polished YouTube edit using:

- transcript-aware cuts
- silence shortening
- retake detection
- captions
- smart punch-ins
- technology/logo B-roll
- motion graphic edit decisions
- FFmpeg rendering
- later: Remotion-based premium graphics

## MVP pipeline

```
Raw video
  -> audio extraction
  -> WhisperX transcription
  -> silence analysis
  -> EditPlan JSON
  -> FFmpeg clean-cut render
  -> captions / graphics / B-roll (next milestone)
```

## Stack

- Python 3.11+
- FastAPI
- FFmpeg
- WhisperX
- Pydantic
- Remotion (Milestone 2)
- Next.js (Milestone 3)

## Local setup

### 1. Install FFmpeg

macOS:

```bash
brew install ffmpeg
```

Ubuntu:

```bash
sudo apt update && sudo apt install -y ffmpeg
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

### 4. Start API

```bash
uvicorn backend.app.main:app --reload
```

Open:

- API: http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

## First test

```bash
curl -X POST http://127.0.0.1:8000/projects/upload \
  -F "file=@/path/to/video.mp4"
```

## Repository safety

Never commit API keys, model tokens, private videos, exports or local asset libraries.

See `.gitignore`.

## Roadmap

### Milestone 1 — Core edit engine
- [x] project structure
- [x] upload API
- [x] EditPlan schema
- [x] FFmpeg audio extraction
- [x] WhisperX service interface
- [ ] silence-to-cut conversion
- [ ] retake detection
- [ ] clean-cut renderer

### Milestone 2 — Premium renderer
- [ ] Remotion project
- [ ] captions
- [ ] smart zoom
- [ ] chapter cards
- [ ] key-point overlays
- [ ] technology logo overlays
- [ ] diagram templates

### Milestone 3 — Visual editor
- [ ] Next.js UI
- [ ] transcript review
- [ ] timeline
- [ ] edit-decision approve/reject
- [ ] preview render

### Milestone 4 — AI director
- [ ] semantic retake detection
- [ ] B-roll selection
- [ ] motion graphic selection
- [ ] chapter generation
- [ ] style learning
