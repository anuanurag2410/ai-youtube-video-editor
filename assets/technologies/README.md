# Data Engineering Visual Asset Library

This folder is the approved visual library used by the AI video editor.

## Standard files inside every technology folder

Add only the assets that are useful. You do not need all four for every tool.

- `logo.png` — transparent official/approved logo
- `ui.png` — clean screenshot of the product UI/workspace
- `diagram.png` — architecture, workflow, or concept diagram
- `broll.png` — optional extra visual/B-roll image

## Recommended image quality

- PNG preferred
- Transparent background for logos
- At least 1000px wide for screenshots/diagrams
- Avoid watermarks
- Avoid tiny compressed web images
- Keep screenshots clean and readable
- Use assets you are comfortable publishing in YouTube videos

## How the editor will use them

1. Detect technology from transcript.
2. Read `manifest.json` / `meta.json`.
3. Prefer the most contextually relevant visual.
4. Animate it with subtle slide/fade/zoom.
5. Return to talking head automatically.

Example:

```
assets/technologies/databricks/
  logo.png
  ui.png
  diagram.png
  broll.png
  meta.json
```

If only `logo.png` exists, the renderer can still use it.
