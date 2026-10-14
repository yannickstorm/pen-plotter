# Plotter Bridge

A small app that sits next to your GRBL pen plotter (on a Raspberry Pi or any computer), streams the G-code over USB, and lets you send and watch plots from any browser on your network.

- **Monitor** at `http://<bridge>:8080/` — live progress, preview of what's drawn so far, time left, pause / resume / stop, jog, pen up/down, console, and "run a G-code file".
- **Plot Studio** at `http://<bridge>:8080/studio` — the full studio, already connected to the plotter.
- The plot keeps running if you close the browser. Open the monitor on your phone to check on it.

Only Python 3 is needed on Linux and macOS (no packages). On Windows, run `pip install pyserial` first.

## Raspberry Pi setup

1. Get the repo onto the Pi: `git clone https://github.com/yannickstorm/pen-plotter` (or copy it over with `scp -r`).
2. Plug the plotter into the Pi's USB port.
3. Install it as a service that starts on boot:

   ```
   cd pen-plotter/bridge
   sudo ./install.sh
   ```

   This copies `bridge.py`, `monitor.html` and the repo's `studio.html` to `/opt/plotter-bridge`. To update later: `git pull`, then run `sudo ./install.sh` again.

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

The same settings can come from the environment: `PLOTTER_PORT`, `PLOTTER_BAUD`, `BRIDGE_PORT`, `BRIDGE_HOST`, `BRIDGE_TOKEN`.

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
- Unplugging the plotter ends the job with an error; the bridge reconnects by itself when the plotter comes back.

## API

All endpoints are under `/api/`, JSON in and out, with CORS enabled.

| | |
|---|---|
| `GET status?since=<seq>` | state, position, job progress / ETA, and log lines after `seq` |
| `GET job` | current job's moves for the preview |
| `GET ports` | serial ports |
| `POST connect {port?, baud?}` / `disconnect` | |
| `POST run {gcode, name?, penUp?}` | start a job (`penUp` = the pen-up S value, used to tell drawing from travel and to lift the pen on stop) |
| `POST pause` / `resume` / `stop {penUp?}` | |
| `POST send {line}` | send a command when no job is running |
| `POST jog {x, y, feed}` / `unlock` / `home` | |
