# Pen Plotter

Tools for a CoreXY pen plotter running GRBL 1.1 with a servo pen (`M3 S0` = pen up, `M3 S35` = pen down), work area 310 × 210 mm.

| File | What it is |
|---|---|
| `server.py` | Local web controller backend (stdlib HTTP + pyserial). `python3 server.py [--port /dev/ttyUSB0] [--http 8000]` |
| `index.html` | Controller UI at `http://127.0.0.1:8000/` — jog, pen, console, stream G-code |
| `studio.html` | **Plot Studio** at `/studio` — converts SVG, images, DXF, G-code, text and patterns into multi-pen line art and G-code, and plots it. Three workspaces: **Design** (objects, pens, paper), **Machine** (your plotters as a list of cards with live status; add one with a setup wizard over a Plotter Bridge, USB or the built-in demo plotter; per machine: control, settings, info) and **Plot** (pen-by-pen queue, live view of the head and of what's drawn, progress and time left, and recovery of interrupted plots). Includes the plot-range styles, with real street maps (OpenStreetMap) and contour maps (Terrarium elevation) and a real star map (**Sternenhimmel**: pick an address, date and time; it plots the stars, constellations, Milky Way, planets and Moon for that moment) that can be moved and zoomed on the sheet (double-click the map) and reload by themselves |
| `bridge/` | **Plotter Bridge** for a Raspberry Pi or another computer next to the plotter: streams jobs over USB, serves a live monitor at `/` (Plot Studio is the hosted one — the bridge keeps no copy), keeps plotting when the browser closes, and saves progress to disk so an interrupted plot can be resumed. Standard library only. See [`bridge/README.md`](bridge/README.md) |
| `build_artifact.py` | Builds the hosted copy of Plot Studio: `python3 build_artifact.py OUT.html [example-image]` |
| `send.py` | Minimal command-line G-code sender |
| `make_*.py` | Scripts that generate individual designs |
| `tests/` | `python3 tests/test_bridge.py`: the bridge's checkpoint and resume against a simulated GRBL (crash mid-stroke, bridge restart, stop, pulled cable, HTTP API). `python3 tests/test_studio.py`: browser tests for Plot Studio with real mouse/touch input — resizing, moving and zooming a map, and a plot on the demo plotter that crashes, is recovered, and survives a page reload (needs Chrome or Chromium and `websockets`). `great-wave.webp` is the test image and the hosted example. |

Plot Studio also works opened directly as a file or hosted; without a plotter it exports G-code / SVG / HPGL, and the **demo plotter** (Machine → Demo plotter, or open the page with `?demo`) shows how plotting, the live view and crash recovery work without hardware.

## Machines and the setup wizard

A *machine* is what a plotter is (drawing area, pen up/down, servo wait, speeds, mirror X, start/end G-code) plus how to reach it. **Machine → Add** runs a wizard: connection → detect (GRBL version, work area, homing) → pen servo (the pen follows the slider) → origin and direction (draws a small “F” so you can see whether X is mirrored) → name and save. The design follows the selected machine: bed size and G-code come from its settings, and a project does not overwrite them.

Where the settings live:

| Connection | Settings are kept | Moving them |
|---|---|---|
| **Plotter Bridge** | on the bridge (`machine.json` next to the plot checkpoint) — the source of truth. Every browser and phone that connects reads them; an edit in one reaches the others within a second. Two edits at once ask which to keep. | nothing to do |
| **USB cable** | in this browser (GRBL has no spare storage), together with the board's USB id so the same plotter is recognised again | *⋯ → Export settings*, then import in the wizard's first step |
| **Demo plotter** | in this browser | same |

## When a plot is interrupted

A long plot can be cut short: GRBL resets (servo brown-outs are common), the USB cable comes out, the computer sleeps, the tab or the bridge crashes. Nothing has to be redone:

- **Progress is saved as it plots** — by the bridge to disk, by the studio (USB) in the browser — every couple of seconds. It counts only lines GRBL has really drawn, not the ones merely queued: lines go out numbered and GRBL reports the one it's executing (`Ln:`), dwells (`G4`) are only answered once every earlier move finished, and the planner can't hold more than ~15 moves.
- **The design is autosaved** in the browser too, so reopening the studio after a crash brings back the project and the unfinished plot.
- **Resume** from the Plot workspace (or the bridge monitor on your phone): it checks whether the controller still knows where the pen is (Home / pen is at 0,0 / pen hasn't moved), then restarts the interrupted stroke from its pen-down after a short preamble (pen up, travel, feed). An earlier or later stroke can be picked.

The demo plotter has buttons to cause a power glitch or pull the cable, so all of this can be tried without risking a real sheet.

**Online:** <https://yannickstorm.github.io/pen-plotter/>. GitHub Pages deploys it from `main` (`.github/workflows/pages.yml`). Over HTTPS in Chrome or Edge it can plot straight to a plotter on USB through Web Serial. To use a Plotter Bridge from this page, the bridge needs an https address (Tailscale Serve is the easy way; see [Plot Studio and https](bridge/README.md#plot-studio-and-https)). Each release also carries `plot-studio.html`, a single file that works offline. To publish a release, push a `v*` tag or run the workflow with a release tag.
