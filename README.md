# Pen Plotter

Tools for a CoreXY pen plotter running GRBL 1.1 with a servo pen (`M3 S0` = pen up, `M3 S35` = pen down), work area 310 × 210 mm.

| File | What it is |
|---|---|
| `server.py` | Local web controller backend (stdlib HTTP + pyserial). `python3 server.py [--port /dev/ttyUSB0] [--http 8000]` |
| `index.html` | Controller UI at `http://127.0.0.1:8000/` — jog, pen, console, stream G-code |
| `studio.html` | **Plot Studio** at `/studio` — converts SVG, images, DXF, G-code, text and patterns into multi-pen line art and G-code; plots pen by pen through the server |
| `build_artifact.py` | Builds the hosted copy of Plot Studio: `python3 build_artifact.py OUT.html [example-image]` |
| `CLAUDE.md`, `.claude/` | Workflow notes and the startup hook for Claude Code cloud sessions; `.github/workflows/tests.yml` runs the tests on every push and PR |
| `send.py` | Minimal command-line G-code sender |
| `make_*.py` | Scripts that generate individual designs |
| `tests/` | Browser tests for Plot Studio with real mouse/touch input: `python3 tests/test_studio.py` (needs Chrome or Chromium — set `$CHROME` if it isn't on PATH — and `pip install -r requirements-dev.txt`). `great-wave.webp` is the test image and the hosted example. |

Plot Studio also works opened directly as a file or hosted; without the server it exports G-code / SVG / HPGL instead of plotting.
