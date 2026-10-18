# Plotter Bridge

A small app that sits next to your GRBL pen plotter (on a Raspberry Pi or any computer), streams the G-code over USB, and lets you send and watch plots from any browser on your network.

- **Monitor** at `http://<bridge>:8080/` — live progress, preview of what's drawn so far, time left, pause / resume / stop, jog, pen up/down, console, and "run a G-code file".
- **Plot Studio** is not part of the bridge. Use the hosted one, <https://yannickstorm.github.io/pen-plotter/>, which is always the newest, and add the bridge in its **Machine** view (the monitor's "Plot Studio" button opens it with this bridge's address filled in). Nothing to update on the Pi but the bridge itself; if the studio is newer than the bridge it still works, just without the newest bridge features. From a browser on an https page the bridge needs an https address, see [Plot Studio and https](#plot-studio-and-https).
- The plot keeps running if you close the browser. Open the monitor on your phone to check on it.
- **Knows its plotter:** the machine's settings (drawing area, pen up/down, servo wait, speeds…) are kept on the bridge, so Plot Studio on any computer or phone — and this monitor — use the same ones. See [Machine settings](#machine-settings).
- **Crash-proof:** the job and how far it got are saved to disk as it plots. After a power cut, a controller reset, a pulled cable or a restart of the bridge, the plot resumes from the stroke it was drawing (see [Resuming an interrupted plot](#resuming-an-interrupted-plot)).

Only Python 3 is needed on Linux and macOS (no packages). On Windows, run `pip install pyserial` first.

## Raspberry Pi setup

1. Download the latest release onto the Pi:

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

   This copies `bridge.py` and `monitor.html` to `/opt/plotter-bridge` (and removes an old `studio.html` there: the studio is not kept on the bridge). The bridge then keeps itself up to date (see [Updates](#updates)); to update by hand, download the new release (or `git pull`) and run `sudo ./install.sh` again.

   Add options at the end, e.g. `sudo ./install.sh --token s3cret --baud 115200`.
4. Open `http://raspberrypi.local:8080/` (use the Pi's IP address if `.local` names don't work on your network).

Logs: `journalctl -u plotter-bridge -f`

## Running it by hand (any computer)

From the `bridge` folder of the repo (when a `studio.html` sits in the folder above, `/studio` serves that copy; handy while developing):

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
| `--state` | `~/.plotter-bridge` | where the running job, its progress and the machine settings are kept |
| `--name` | the computer's name | the plotter's name in Plot Studio |
| `--cert`, `--key` | none | serve https with this certificate (PEM; omit `--key` if the file holds the key too) |
| `--studio-url` | the hosted studio | where `/studio` redirects to and the monitor links |

The same settings can come from the environment: `PLOTTER_PORT`, `PLOTTER_BAUD`, `BRIDGE_PORT`, `BRIDGE_HOST`, `BRIDGE_TOKEN`, `BRIDGE_STATE`, `BRIDGE_NAME`, `BRIDGE_CERT`, `BRIDGE_KEY`, `BRIDGE_STUDIO_URL`.

## Machine settings

`machine.json` in `--state` holds the plotter's name, a permanent id and its settings (`bedW`, `bedH`, `up`, `down`, `dwell`, `feed`, `travel`, `travelG0`, `parkX`, `parkY`, `park`, `mirrorX`, `decimals`, `header`, `footer`), with a revision that counts saves. Add the plotter from Plot Studio (Machine → Add → Plotter Bridge): the wizard reads what GRBL reports, sets up the pen, checks the direction and saves the result here. The id lets a browser recognise the bridge again after its address or name changes. The monitor reads the pen values and drawing area from these settings; change them in Plot Studio.

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

## Plot Studio and https

Browsers refuse to let an https page (like the hosted Plot Studio) talk to a plain `http://` address, except `http://localhost`. The bridge speaks http, so the hosted studio needs it to have an **https address**. The easiest way is [Tailscale](https://tailscale.com), which also lets you reach the plotter from anywhere without opening your router:

1. Install Tailscale on the Pi (`curl -fsSL https://tailscale.com/install.sh | sh`, then `sudo tailscale up` and log in) and on your phone and laptop, with the same account.
2. In the Tailscale admin page turn on **MagicDNS** and **HTTPS certificates** (a one-time switch).
3. On the Pi run `tailscale serve --bg 8080`. It prints an address like `https://raspberrypi.tail1234.ts.net`. (Tailscale has changed this command's syntax between versions; `tailscale serve --help` shows the current form.)
4. In Plot Studio: **Machine → Add → Plotter Bridge**, and enter that address.

Only devices logged in to your Tailscale account can reach it. **Don't use `tailscale funnel`**, which would put the bridge on the public internet; the bridge has no security beyond its optional token. You can also start the bridge with `--host 127.0.0.1` so it is only reachable through Tailscale.

Other ways: any reverse proxy that gives the bridge an https address (Caddy, nginx), or `--cert`/`--key` when you have a certificate for the bridge's name. A self-signed certificate works only after each device has been told to trust it, which is awkward on phones.

Without https: open a downloaded `plot-studio.html` (a file, not an https page) or the repo's `studio.html` and add the bridge by its `http://` address, including a Tailscale IP such as `http://100.x.y.z:8080`. Plotting over USB from the studio needs no bridge at all (Chrome or Edge).

The copy of Plot Studio inside claude.ai can't reach USB devices or your local network. Projects are saved per browser address, so move work between them with **File → Save project / Open**.

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
| `GET machine` | `{machine: {id, name, rev, profile, updated}}` — `profile` is `null` until set up |
| `POST machine {name?, profile?, baseRev?}` | save the settings. Unknown or out-of-range values are refused; a `baseRev` that is behind answers `{conflict: true, machine}` instead of overwriting |
| `GET info` | `{name: 'plotter-bridge', id, machine, version, auth}` — no token needed, used to recognise the bridge |
| `GET job?gcode=1` | the job's moves, stroke starts, resume point (and its lines) |
| `POST job/resume {from?}` | resume a stopped or interrupted job from line `from` (default: the start of the interrupted stroke) |
| `POST job/discard` | forget the job and its checkpoint |

`status` also carries `machine_rev` (to notice settings changes) and `grbl` (`version` and the settings the controller reported: `$22`, `$110`, `$111`, `$130`, `$131`…). It reports the job's `state` (`running`, `finished`, `stopped`, `failed`, `interrupted`), `done` (lines drawn), `resumable`, `resume_at` and `pos` (where the pen was when it stopped).

## Updates

Plot Studio's **Machine → Software** tab (for a bridge machine) lists the releases of `yannickstorm/pen-plotter` with their notes, installs any of them (a newer one, or an older one to go back), and sets how the bridge updates itself:

- **Install** (default): every few hours (and a minute after start) the bridge looks for a newer release and installs it as soon as the plotter is idle.
- **Tell me**: it looks, shows "a new release is available", and waits for you to press *Update*.
- **Off**: it never looks by itself; you can still check and install from the tab.

Installing downloads `plotter-bridge.tar.gz`, checks it (the sha256 GitHub lists for the file, then that the new `bridge.py` compiles and carries the release's version), replaces `bridge.py` and `monitor.html` (the old ones stay as `*.prev`) and restarts the bridge. It is **never done while a plot is running**: an automatic update waits, a manual install is refused. Pre-releases are listed but not installed.

- The choice is kept on the bridge in `update.json` in the state folder (`--state`).
- `GET api/releases` lists the releases; `POST api/update` checks now; `POST api/update/config {mode, hours}`; `POST api/update/install {tag}`; `GET api/info` carries `update: {current, latest, available, state, checked, error, mode, hours}`.
- `--no-update` (or `BRIDGE_NO_UPDATE=1`) removes all of it; `--update-hours N` and `--update-repo owner/name` set the first-start defaults.
- The install folder must be writable by the service user: `install.sh` does that. A bridge installed with an older `install.sh` needs one `sudo ./install.sh` first (or `sudo chown -R pi /opt/plotter-bridge`).
- To go back by hand: copy `bridge.py.prev` over `bridge.py`.
