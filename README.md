# Pen Plotter

Tools for a CoreXY pen plotter running GRBL 1.1 with a servo pen (`M3 S0` = pen up, `M3 S35` = pen down), work area 310 × 210 mm.

| File | What it is |
|---|---|
| `server.py` | Local web controller backend (stdlib HTTP + pyserial). `python3 server.py [--port /dev/ttyUSB0] [--http 8000]` |
| `index.html` | Controller UI at `http://127.0.0.1:8000/` — jog, pen, console, stream G-code |
| `studio.html` | **Plot Studio** at `/studio` — converts SVG, images, DXF, G-code, text and patterns into multi-pen line art and G-code; plots pen by pen through the server |
| `bridge/` | **Plotter Bridge** for a Raspberry Pi or another computer next to the plotter: streams jobs over USB, serves a live monitor at `/` and Plot Studio at `/studio`, and keeps plotting when the browser closes. Standard library only. See [`bridge/README.md`](bridge/README.md) |
| `build_artifact.py` | Builds the hosted copy of Plot Studio: `python3 build_artifact.py OUT.html [example-image]` |
| `send.py` | Minimal command-line G-code sender |
| `make_*.py` | Scripts that generate individual designs |
| `tests/` | Browser tests for Plot Studio with real mouse/touch input: `python3 tests/test_studio.py` (needs google-chrome and `websockets`). `great-wave.webp` is the test image and the hosted example. |

Plot Studio also works opened directly as a file or hosted; without the server it exports G-code / SVG / HPGL instead of plotting.

**Online:** <https://yannickstorm.github.io/pen-plotter/>. GitHub Pages deploys it from `main` (`.github/workflows/pages.yml`). Over HTTPS in Chrome or Edge it can plot straight to a plotter on USB through Web Serial. Each release also carries `plot-studio.html`, a single file that works offline. To publish a release, push a `v*` tag or run the workflow with a release tag.
