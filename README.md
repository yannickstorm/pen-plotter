# Pen Plotter

Tools for a CoreXY pen plotter running GRBL 1.1 with a servo pen (`M3 S0` = pen up, `M3 S35` = pen down), work area 310 × 210 mm.

| File | What it is |
|---|---|
| `server.py` | Local web controller backend (stdlib HTTP + pyserial). `python3 server.py [--port /dev/ttyUSB0] [--http 8000]` |
| `index.html` | Controller UI at `http://127.0.0.1:8000/` — jog, pen, console, stream G-code |
| `studio.html` | **Plot Studio** at `/studio` — converts SVG, images, DXF, G-code, text and patterns into multi-pen line art and G-code, and plots it. Three workspaces: **Design** (objects, pens, paper), **Machine** (connect over USB, a Plotter Bridge or the built-in demo plotter; jog, pen, origin, settings, servo test, console) and **Plot** (pen-by-pen queue, live view of the head and of what's drawn, progress and time left, and recovery of interrupted plots). Includes the plot-range styles, with real street maps (OpenStreetMap) and contour maps (Terrarium elevation) that can be moved and zoomed on the sheet (double-click the map) and reload by themselves |
| `bridge/` | **Plotter Bridge** for a Raspberry Pi or another computer next to the plotter: streams jobs over USB, serves a live monitor at `/` and Plot Studio at `/studio`, keeps plotting when the browser closes, and saves progress to disk so an interrupted plot can be resumed. Standard library only. See [`bridge/README.md`](bridge/README.md) |
| `build_artifact.py` | Builds the hosted copy of Plot Studio: `python3 build_artifact.py OUT.html [example-image]` |
| `send.py` | Minimal command-line G-code sender |
| `make_*.py` | Scripts that generate individual designs |
| `tests/` | `python3 tests/test_bridge.py`: the bridge's checkpoint and resume against a simulated GRBL (crash mid-stroke, bridge restart, stop, pulled cable, HTTP API). `python3 tests/test_studio.py`: browser tests for Plot Studio with real mouse/touch input — resizing, moving and zooming a map, and a plot on the demo plotter that crashes, is recovered, and survives a page reload (needs Chrome or Chromium and `websockets`). `great-wave.webp` is the test image and the hosted example. |

Plot Studio also works opened directly as a file or hosted; without a plotter it exports G-code / SVG / HPGL, and the **demo plotter** (Machine → Demo plotter, or open the page with `?demo`) shows how plotting, the live view and crash recovery work without hardware.

## When a plot is interrupted

A long plot can be cut short: GRBL resets (servo brown-outs are common), the USB cable comes out, the computer sleeps, the tab or the bridge crashes. Nothing has to be redone:

- **Progress is saved as it plots** — by the bridge to disk, by the studio (USB) in the browser — every couple of seconds. It counts only lines GRBL has really drawn, not the ones merely queued: lines go out numbered and GRBL reports the one it's executing (`Ln:`), dwells (`G4`) are only answered once every earlier move finished, and the planner can't hold more than ~15 moves.
- **The design is autosaved** in the browser too, so reopening the studio after a crash brings back the project and the unfinished plot.
- **Resume** from the Plot workspace (or the bridge monitor on your phone): it checks whether the controller still knows where the pen is (Home / pen is at 0,0 / pen hasn't moved), then restarts the interrupted stroke from its pen-down after a short preamble (pen up, travel, feed). An earlier or later stroke can be picked.

The demo plotter has buttons to cause a power glitch or pull the cable, so all of this can be tried without risking a real sheet.

**Online:** <https://yannickstorm.github.io/pen-plotter/>. GitHub Pages deploys it from `main` (`.github/workflows/pages.yml`). Over HTTPS in Chrome or Edge it can plot straight to a plotter on USB through Web Serial. Each release also carries `plot-studio.html`, a single file that works offline. To publish a release, push a `v*` tag or run the workflow with a release tag.
