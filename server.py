#!/usr/bin/env python3
"""Pen plotter web UI backend (stdlib http.server + pyserial).

Run:  python3 server.py [--port /dev/ttyUSB0] [--http 8000]
Then open http://127.0.0.1:8000
"""
import argparse
import json
import queue
import math
import re
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import serial

BAUD = 115200
WORK_X, WORK_Y = 310.0, 210.0  # GRBL $130/$131 max travel, work coords start at 0,0
PEN_UP, PEN_DOWN = 0, 35  # servo S values found by testing
HERE = Path(__file__).parent

NUM = r"(-?\d+\.\d+)"
RX_BUFFER = 127  # GRBL serial RX buffer is 128 bytes; keep one spare
# GRBL 0.9: <Idle,MPos:...,WPos:x,y,z>   GRBL 1.1 ($10=0): <Idle|WPos:x,y,z|FS:0,0>  (state may be "Hold:0")
STATUS_RE = re.compile(rf"<(\w+)[,|:].*WPos:{NUM},{NUM},{NUM}(?:\|.*)?>$")


class Plotter:
    def __init__(self, port):
        self.port = port
        self.ser = None
        self.write_lock = threading.Lock()  # one command at a time
        self.replies = queue.Queue()  # "ok" / "error:..." lines, in the order GRBL sends them
        self.state = "Disconnected"
        self.pos = [0.0, 0.0, 0.0]
        self.pen = None  # last S value sent
        self.log = []  # (seq, text)
        self.seq = 0
        self.job = {"running": False, "sent": 0, "total": 0, "error": None}
        self.abort = threading.Event()

    # --- logging -------------------------------------------------------
    def _log(self, text):
        self.seq += 1
        self.log.append((self.seq, text))
        del self.log[:-300]

    # --- connection ----------------------------------------------------
    @property
    def connected(self):
        return self.ser is not None and self.ser.is_open

    def connect(self):
        if self.connected:
            return
        self.ser = serial.Serial(self.port, BAUD, timeout=0.2)
        self.state = "Connecting"
        threading.Thread(target=self._reader, args=(self.ser,), daemon=True).start()
        threading.Thread(target=self._poller, args=(self.ser,), daemon=True).start()
        time.sleep(2.5)  # opening the port resets the board
        self.pen = None

    def disconnect(self):
        if not self.connected:
            return
        self.abort.set()
        try:
            self.ser.write(b"M5\n")  # leave the pen up
            self.ser.flush()
            time.sleep(0.2)
        finally:
            self.ser.close()
            self.state = "Disconnected"

    def _reader(self, ser):
        buf = b""
        while ser.is_open:
            try:
                data = ser.read(64)
            except (serial.SerialException, OSError, TypeError):
                break
            if not data:
                continue
            buf += data
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                line = raw.decode(errors="replace").strip()
                if line:
                    try:
                        self._handle(line)
                    except Exception as e:  # noqa: BLE001 - a bad line must never kill the reader
                        self._log(f"! ignored unreadable line {line!r} ({e})")
        self.state = "Disconnected"

    def _handle(self, line):
        if line.startswith("<"):
            m = STATUS_RE.match(line)
            if m:
                self.state = m.group(1)
                self.pos = [float(m.group(i)) for i in (2, 3, 4)]
            else:
                self._log(f"! ignored garbled status {line!r}")  # serial noise; next poll fixes it
            return
        self._log(f"< {line}")
        if line == "ok" or line.startswith("error"):
            self.replies.put(line)

    def _poller(self, ser):
        while ser.is_open:
            try:
                ser.write(b"?")
            except (serial.SerialException, OSError, TypeError):
                break
            time.sleep(0.25)

    # --- sending -------------------------------------------------------
    def send(self, line, timeout=60):
        """Send one line and wait for ok/error. Returns the reply."""
        if not self.connected:
            raise RuntimeError("not connected")
        with self.write_lock:
            self._drain_replies()
            self._log(f"> {line}")
            self.ser.write((line + "\n").encode())
            try:
                return self.replies.get(timeout=timeout)
            except queue.Empty:
                raise RuntimeError(f"timeout waiting for reply to {line!r}") from None

    def _drain_replies(self):
        while True:
            try:
                self.replies.get_nowait()
            except queue.Empty:
                return

    def set_pen(self, s):
        s = max(0, min(255, int(s)))
        reply = self.send(f"M3 S{s}")
        if reply == "ok":
            self.pen = s
        return reply

    def move(self, x, y, feed, pen_lift=True):
        x = max(0.0, min(WORK_X, float(x)))
        y = max(0.0, min(WORK_Y, float(y)))
        return self.send(f"G90 G1 X{x:.3f} Y{y:.3f} F{float(feed):.0f}")

    def jog(self, dx, dy, feed):
        return self.move(self.pos[0] + float(dx), self.pos[1] + float(dy), feed)

    def stop(self):
        """Feed hold + soft reset. Work position may be lost if it was moving."""
        self.abort.set()
        if self.connected:
            self.ser.write(b"!")
            time.sleep(0.1)
            self.ser.write(b"\x18")
            self._log("> STOP (hold + reset)")
            self.replies.put("error:stopped")  # wake up anyone waiting for a reply
            self.pen = None

    def resume(self):
        """Cycle start: continue after a feed hold or an M0 pause (e.g. a pen change)."""
        if not self.connected:
            raise RuntimeError("not connected")
        self.ser.write(b"~")
        self._log("> RESUME (~)")

    # --- g-code streaming ---------------------------------------------
    def run_gcode(self, text):
        lines = []
        for raw in text.splitlines():
            line = re.sub(r"\(.*?\)|;.*", "", raw).strip()
            if line:
                lines.append(line)
        if self.job["running"]:
            raise RuntimeError("a job is already running")
        if not self.connected:
            raise RuntimeError("not connected")
        self.abort.clear()
        self.job.update(running=True, sent=0, total=len(lines), error=None)
        threading.Thread(target=self._stream, args=(lines,), daemon=True).start()

    def _stream(self, lines):
        """Character-counting streaming: keep GRBL's RX buffer full so its planner
        can look ahead and blend consecutive segments instead of stopping at each one."""
        try:
            with self.write_lock:
                self._drain_replies()
                inflight = []  # (line number, text) sent but not yet acknowledged
                used = 0  # bytes of `inflight` sitting in GRBL's RX buffer
                nxt = 0
                while nxt < len(lines) or inflight:
                    if self.abort.is_set():
                        self.job["error"] = "stopped"
                        break
                    # send as many lines as fit in the buffer
                    while nxt < len(lines) and used + len(lines[nxt]) + 1 <= RX_BUFFER:
                        line = lines[nxt]
                        self.ser.write((line + "\n").encode())
                        nxt += 1
                        inflight.append((nxt, line))
                        used += len(line) + 1
                    if nxt < len(lines) and not inflight:
                        raise RuntimeError(f"line {nxt + 1} is longer than GRBL's buffer")
                    try:
                        reply = self.replies.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    i, line = inflight.pop(0)
                    used -= len(line) + 1
                    if reply != "ok":
                        self.job["error"] = f"{reply} on line {i}: {line}"
                        self.abort.set()
                        break
                    self.job["sent"] = i
            if not self.abort.is_set():
                self.send(f"M3 S{PEN_UP}")  # finish with the pen up
        except Exception as e:  # noqa: BLE001
            self.job["error"] = str(e)
        finally:
            self.job["running"] = False

    def snapshot(self, since):
        return {
            "connected": self.connected,
            "port": self.port,
            "state": self.state,
            "pos": self.pos,
            "pen": self.pen,
            "job": self.job,
            "work": [WORK_X, WORK_Y],
            "log": [[n, t] for n, t in self.log if n > since],
            "seq": self.seq,
        }


def build_shape(d):
    """Return (gcode, points) for a shape request; points are sampled for bounds checks."""
    f = float(d.get("feed", 3000))
    up, down = int(d.get("up", PEN_UP)), int(d.get("down", PEN_DOWN))
    kind = d["kind"]
    g, pts = [], []

    def travel(x, y):
        g.append(f"M3 S{up}")
        g.append("G4 P0.3")
        g.append(f"G1 X{x:.3f} Y{y:.3f} F{f:.0f}")
        g.append(f"M3 S{down}")
        g.append("G4 P0.3")
        pts.append((x, y))

    def line(x, y):
        g.append(f"G1 X{x:.3f} Y{y:.3f} F{f:.0f}")
        pts.append((x, y))

    if kind == "line":
        travel(float(d["x1"]), float(d["y1"]))
        line(float(d["x2"]), float(d["y2"]))
    elif kind == "rect":
        x, y, w, h = (float(d[k]) for k in ("x", "y", "w", "h"))
        travel(x, y)
        for px, py in ((x + w, y), (x + w, y + h), (x, y + h), (x, y)):
            line(px, py)
    elif kind in ("circle", "arc"):
        cx, cy, r = (float(d[k]) for k in ("cx", "cy", "r"))
        if r <= 0:
            raise ValueError("radius must be positive")
        a0 = math.radians(float(d.get("a0", 0)))
        a1 = a0 + 2 * math.pi if kind == "circle" else math.radians(float(d["a1"]))
        ccw = bool(d.get("ccw", True))
        sweep = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
        if kind == "circle":
            sweep = 2 * math.pi if ccw else -2 * math.pi
        elif sweep == 0:
            raise ValueError("start and end angle are the same")
        sx, sy = cx + r * math.cos(a0), cy + r * math.sin(a0)
        ex, ey = cx + r * math.cos(a0 + sweep), cy + r * math.sin(a0 + sweep)
        travel(sx, sy)
        g.append(f"G{3 if ccw else 2} X{ex:.3f} Y{ey:.3f} I{cx - sx:.3f} J{cy - sy:.3f} F{f:.0f}")
        pts.extend((cx + r * math.cos(a0 + sweep * i / 72), cy + r * math.sin(a0 + sweep * i / 72)) for i in range(73))
    else:
        raise ValueError(f"unknown shape {kind!r}")
    g.append(f"M3 S{up}")
    return "\n".join(["G90"] + g), pts


def check_bounds(pts):
    for x, y in pts:
        if not (0 <= x <= WORK_X and 0 <= y <= WORK_Y):
            raise ValueError(f"shape leaves the work area (reaches X{x:.1f} Y{y:.1f}; limits 0-{WORK_X:.0f} / 0-{WORK_Y:.0f})")


def gcode_points(text):
    """Absolute-mode path points (arcs sampled) of a job; rejects relative mode."""
    x = y = 0.0
    pts, mode = [], None
    for raw in text.splitlines():
        line = re.sub(r"\(.*?\)|;.*", "", raw).upper()
        if re.search(r"\bG91\b", line):
            raise ValueError("relative mode (G91) is not supported in jobs")
        if re.search(r"\bG92\b|\bG10\b", line):
            continue
        g = re.search(r"\bG0?([0-3])\b", line)
        if g:
            mode = int(g.group(1))
        w = {k: float(v) for k, v in re.findall(r"([XYIJ])\s*(-?\d*\.?\d+)", line)}
        if mode is None or ("X" not in w and "Y" not in w):
            continue
        nx, ny = w.get("X", x), w.get("Y", y)
        if mode in (2, 3) and ("I" in w or "J" in w):
            cx, cy = x + w.get("I", 0), y + w.get("J", 0)
            r = math.hypot(x - cx, y - cy)
            a0, a1 = math.atan2(y - cy, x - cx), math.atan2(ny - cy, nx - cx)
            sweep = (a1 - a0) % (2 * math.pi) if mode == 3 else -((a0 - a1) % (2 * math.pi))
            if sweep == 0:
                sweep = 2 * math.pi if mode == 3 else -2 * math.pi
            pts.extend((cx + r * math.cos(a0 + sweep * i / 72), cy + r * math.sin(a0 + sweep * i / 72)) for i in range(73))
        pts.append((nx, ny))
        x, y = nx, ny
    return pts


plotter = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        page = {"/": "index.html", "/index.html": "index.html", "/studio": "studio.html", "/studio.html": "studio.html"}.get(self.path)
        if page:
            body = (HERE / page).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/status"):
            since = 0
            if "since=" in self.path:
                since = int(self.path.split("since=")[1].split("&")[0] or 0)
            self._json(plotter.snapshot(since))
        else:
            self.send_error(404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, 400)
        p = self.path
        try:
            if p == "/api/connect":
                plotter.connect()
            elif p == "/api/disconnect":
                plotter.disconnect()
            elif p == "/api/stop":
                plotter.stop()
            elif p == "/api/resume":
                plotter.resume()
            elif p == "/api/command":
                return self._json({"reply": plotter.send(str(data["cmd"]).strip())})
            elif p == "/api/pen":
                return self._json({"reply": plotter.set_pen(data["s"])})
            elif p == "/api/jog":
                return self._json({"reply": plotter.jog(data["dx"], data["dy"], data.get("feed", 3000))})
            elif p == "/api/goto":
                return self._json({"reply": plotter.move(data["x"], data["y"], data.get("feed", 3000))})
            elif p == "/api/zero":
                return self._json({"reply": plotter.send("G92 X0 Y0")})
            elif p == "/api/shape":
                gcode, pts = build_shape(data)
                check_bounds(pts)
                plotter.run_gcode(gcode)
                return self._json({"ok": True, "gcode": gcode})
            elif p == "/api/run":
                check_bounds(gcode_points(str(data["gcode"])))
                plotter.run_gcode(str(data["gcode"]))
            else:
                return self.send_error(404)
        except Exception as e:  # noqa: BLE001
            return self._json({"error": str(e)}, 400)
        self._json({"ok": True})


def main():
    global plotter
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--http", type=int, default=8000)
    args = ap.parse_args()
    plotter = Plotter(args.port)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.http), Handler)  # local only
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt))
    print(f"UI on http://127.0.0.1:{args.http}  (serial {args.port})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        plotter.disconnect()  # pen up + close port
        httpd.server_close()
        print("port closed")


if __name__ == "__main__":
    main()
