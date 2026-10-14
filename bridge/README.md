# Plotter Bridge

A small app that sits next to your GRBL pen plotter (on a Raspberry Pi or any computer), streams the G-code over USB, and lets you send and watch plots from any browser on your network.

- **Monitor** at `http://<bridge>:8080/` — live progress, preview of what's drawn so far, time left, pause / resume / stop, jog, pen up/down, console, and "run a G-code file".
- **Plot Studio** at `http://<bridge>:8080/studio` — the full studio, already connected to the plotter.
- The plot keeps running if you close the browser. Open the monitor on your phone to check on it.
- **Crash-proof:** the job and how far it got are saved to disk as it plots. After a power cut, a controller reset, a pulled cable or a restart of the bridge, the plot resumes from the stroke it was drawing (see [Resuming an interrupted plot](#resuming-an-interrupted-plot)).

Only Python 3 is needed on Linux and macOS (no packages). On Windows, run `pip install pyserial` first.

## Raspberry Pi setup

1. Download the latest release onto the Pi (it contains the bridge and `studio.html`):

   ```
   curl -L https://github.com/yannickstorm/pen-plotter/releases/latest/download/plotter-bridge.tar.gz | tar xz
   ```

   Or use the repo: `git clone https://github.com/yannickstorm/pen-plotter` and work in `pen-plotter/bridge`.
2. Plug the plotter into the Pi's USB port.
3. Install it as a service that starts on boot:

   ```
   cd plotter-bridge          # pen-plotter/bridge for a clone
   sudo ./install.sh
   ```

   This copies `bridge.py`, `monitor.html` and `studio.html` to `/opt/plotter-bridge`. To update later: download the new release (or `git pull`), then run `sudo ./install.sh` again.

   Add options at the end, e.g. `sudo ./install.sh --token s3cret --baud 115200`.
4. Open `http://raspberrypi.local:8080/` (use the Pi's IP address if `.local` names don't work on your network).

Logs: `journalctl -u plotter-bridge -f`

## Running it by hand (any computer)

From the `bridge` folder of the repo (it serves the repo's `studio.html` from the folder above):

```
python3 bridge.py                         # auto-detect the plotter, listen on port 8080
python3 bridge.py --port /dev/ttyUSB0     # pick the port (COM3 on Windows)
python3 bridge.py --token s3cret          # require a token for the API
```

| Option | Default | |
|---|---|---|
| `--port` | auto | serial port of the plotter |
| `--baud` | 115200 | GRBL's baud rate |
| `--http-port` | 8080 | web port |
| `--host` | 0.0.0.0 | `127.0.0.1` to allow this computer only |
| `--token` | none | required as `X-Bridge-Token` header for every API call |
| `--no-autoconnect` | off | only connect when asked from the web page |
| `--state` | `~/.plotter-bridge` | where the running job and its progress are kept for resuming |

The same settings can come from the environment: `PLOTTER_PORT`, `PLOTTER_BAUD`, `BRIDGE_PORT`, `BRIDGE_HOST`, `BRIDGE_TOKEN`, `BRIDGE_STATE`.

## Resuming an interrupted plot

When a plot stops before the end — the controller resets (a brown-out from the servo is a classic), the cable comes out, the Pi loses power, you press Stop to refill a pen, or GRBL rejects a line — the monitor and Plot Studio show an **Unfinished plot** card:

1. Check the paper hasn't moved.
2. Make sure the plotter knows where the pen is. The card compares the position the plotter reports now with where the pen stopped. If they differ, the controller restarted: **Home** it (if it has limit switches), or move the pen to the origin by hand and press **Pen is at 0, 0**, or — if nobody touched the machine — press **Pen hasn't moved**, which tells GRBL the pen is where it stopped (`G10 L20`).
3. **Resume plot**. It starts at the pen-down of the stroke that was being drawn, so that stroke is drawn whole (a few millimetres traced twice don't show; a gap does). `−` / `+` pick an earlier or later stroke; the preview shows in orange what will be traced again.

The bridge also survives itself crashing: a job that was plotting when the bridge stopped is offered for resuming when it starts again.

**How it knows how far it got.** GRBL answers `ok` when a line is queued, not when it's drawn — up to 15 moves can be waiting in its planner. So the bridge counts a line as *drawn* only when it is sure:

- every line goes out numbered (`N1234 G1 …`), and GRBL 1.1's status report says which line it is executing (`Ln:1234`);
- a `G4` dwell (the servo wait after each pen up/down) is only answered after every earlier move has finished;
- once more moves have been answered than the planner holds, the oldest of them has run (the planner size is read from `$I`).

That count is written to `--state` every 2 s (and on every stop), atomically, so a power cut leaves either the old or the new checkpoint, never half of one. Resuming sends a short preamble first: pen up, servo wait, travel to the stroke's start, restore feed and modes.

"Set 0,0 here" in the monitor uses `G10 L20 P1`, which GRBL keeps through resets (unlike `G92`).

## Three ways to plot from Plot Studio

| | How | Browser must stay open? |
|---|---|---|
| **Studio on the bridge** | open `http://<bridge>:8080/studio` | no |
| **USB from your computer** | plotter on your computer's USB; in Plot Studio click the plotter chip → *USB cable* → *Choose port…* (Chrome or Edge) | yes |
| **Studio file → bridge** | open a downloaded `plot-studio.html` (or the repo's `studio.html`) and connect to the bridge address | no |

The copy of Plot Studio inside claude.ai can't reach USB devices or your local network — use one of the above to plot. The GitHub Pages copy is served over https, so it can use USB but can't reach an http bridge; open the studio on the bridge instead. Projects are saved per browser address, so move work between them with **File → Save project / Open**.

## Watching from outside your home network

The bridge has no internet-facing security beyond the optional token. Don't port-forward it. Use [Tailscale](https://tailscale.com) (install it on the Pi and your phone, then open `http://<pi-tailscale-name>:8080/`) or a similar VPN.

## How it works

- Streams with GRBL's character-counting protocol (keeps GRBL's 128-byte receive buffer full without overflowing), polls `?` four times a second for state and position.
- **Pause** = feed hold (`!`), **Resume** = cycle start (`~`). An `M0` in a file pauses the same way.
- **Stop** = feed hold, wait for the machine to stop, soft reset (`Ctrl-X`), then lift the pen (`M3 S<pen up>`). Waiting first keeps GRBL's position, so you normally don't need to re-home.
- A GRBL `error:` during a plot stops the job and reports the line. An `ALARM` stops it; unlock (`$X`) or home (`$H`) from the monitor.
- Bed size is read from GRBL's `$130` / `$131` and Plot Studio adopts it when it connects.
- Unplugging the plotter interrupts the job (it can be resumed); the bridge reconnects by itself when the plotter comes back.

## API

All endpoints are under `/api/`, JSON in and out, with CORS enabled.

| | |
|---|---|
| `GET status?since=<seq>` | state, position, job progress / ETA, and log lines after `seq` |
| `GET job` | current job's moves for the preview |
| `GET ports` | serial ports |
| `POST connect {port?, baud?}` / `disconnect` | |
| `POST run {gcode, name?, penUp?, dwell?, meta?}` | start a job (`penUp` = the pen-up S value, used to tell drawing from travel and to lift the pen on stop; `meta` is kept with the job, e.g. the pen) |
| `POST pause` / `resume` / `stop {penUp?}` | |
| `POST send {line}` | send a command when no job is running |
| `POST jog {x, y, feed}` / `unlock` / `home` | |
| `POST origin {x?, y?}` | the pen's current position becomes work position x, y (default 0, 0) |
| `GET job?gcode=1` | the job's moves, stroke starts, resume point (and its lines) |
| `POST job/resume {from?}` | resume a stopped or interrupted job from line `from` (default: the start of the interrupted stroke) |
| `POST job/discard` | forget the job and its checkpoint |

`status` reports the job's `state` (`running`, `finished`, `stopped`, `failed`, `interrupted`), `done` (lines drawn), `resumable`, `resume_at` and `pos` (where the pen was when it stopped).
