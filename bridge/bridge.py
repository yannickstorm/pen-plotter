#!/usr/bin/env python3
"""
Plotter Bridge — streams G-code to a GRBL pen plotter over USB serial and lets
Plot Studio (or any browser) send jobs and monitor them over the network.

  python3 bridge.py                      # auto-detect the plotter, serve on :8080
  python3 bridge.py --port /dev/ttyUSB0 --baud 115200 --token s3cret

Open http://<this-computer>:8080/ for the live monitor and
Plot Studio is not part of the bridge: use the hosted copy (--studio-url) and add this bridge in its
Machine view. From a browser on an https page, the bridge needs an https address (Tailscale Serve,
or --cert/--key). When a studio.html sits next to bridge.py or in the folder above (running from a
clone), /studio serves that copy instead.

The running job and its progress are saved to disk (--state, default ~/.plotter-bridge) every
couple of seconds. After a crash, a power cut, a controller reset or an unplugged cable, the plot
can be resumed from the stroke it was drawing.

Only the Python 3 standard library is needed on Linux and macOS. On Windows,
install pyserial (pip install pyserial); it is also used on Linux/macOS when present.
"""
import argparse, collections, glob, json, math, os, re, select, socket, ssl, sys, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = '1.0.0'
STUDIO_URL = 'https://yannickstorm.github.io/pen-plotter/'
HERE = os.path.dirname(os.path.abspath(__file__))
RX_BUFFER = 127           # GRBL's serial RX buffer is 128 bytes; keep one spare
STATUS_EVERY = 0.25       # seconds between '?' status queries

# ---------------------------------------------------------------------------
#  serial port: pyserial when installed, otherwise plain termios (Linux/macOS)
# ---------------------------------------------------------------------------
try:
    import serial as _pyserial            # type: ignore
    import serial.tools.list_ports as _lp  # type: ignore
except Exception:
    _pyserial = None


class SerialPort:
    def __init__(self, path, baud):
        self.path, self.baud = path, baud
        if _pyserial:
            self.s = _pyserial.Serial(path, baud, timeout=0.1, write_timeout=2)
            self.fd = None
            return
        import termios
        speed = getattr(termios, f'B{baud}', None)
        if speed is None:
            raise RuntimeError(f'Baud rate {baud} needs pyserial (pip install pyserial)')
        self.fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        a = termios.tcgetattr(self.fd)
        a[0] = 0                                                        # iflag: raw
        a[1] = 0                                                        # oflag: raw
        a[2] = termios.CS8 | termios.CREAD | termios.CLOCAL             # cflag: 8N1
        a[3] = 0                                                        # lflag: raw
        a[4] = a[5] = speed
        a[6][termios.VMIN] = 0
        a[6][termios.VTIME] = 0
        termios.tcsetattr(self.fd, termios.TCSANOW, a)
        termios.tcflush(self.fd, termios.TCIOFLUSH)

    def read(self, timeout=0.1):
        if self.fd is None:
            return self.s.read(self.s.in_waiting or 1)
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return b''
        data = os.read(self.fd, 1024)
        if not data:                      # readable but empty: the device went away
            raise OSError('Serial device disconnected')
        return data

    def write(self, data):
        if self.fd is None:
            self.s.write(data)
            return
        view = memoryview(data)
        deadline = time.time() + 2
        while view:
            try:
                n = os.write(self.fd, view)
                view = view[n:]
            except BlockingIOError:
                if time.time() > deadline:
                    raise OSError('Serial write timed out')
                select.select([], [self.fd], [], 0.05)

    def close(self):
        try:
            self.s.close() if self.fd is None else os.close(self.fd)
        except Exception:
            pass


def list_ports():
    if _pyserial:
        return [{'path': p.device, 'desc': p.description or ''} for p in _lp.comports()]
    found = []
    for pat in ('/dev/serial/by-id/*', '/dev/ttyUSB*', '/dev/ttyACM*', '/dev/ttyAMA*', '/dev/cu.usb*', '/dev/cu.wchusb*', '/dev/tty.usb*'):
        for p in sorted(glob.glob(pat)):
            found.append({'path': p, 'desc': os.path.basename(os.path.realpath(p)) if 'by-id' in p else ''})
    return found


def guess_port():
    ports = [p['path'] for p in list_ports()]
    for pref in ('/dev/serial/by-id/', '/dev/ttyUSB', '/dev/ttyACM', '/dev/cu.usb', 'COM'):
        for p in ports:
            if p.startswith(pref):
                return p
    return ports[0] if ports else None


# ---------------------------------------------------------------------------
#  G-code helpers
# ---------------------------------------------------------------------------
_COMMENT = re.compile(r'\(.*?\)|;.*$')
_WORD = re.compile(r'([A-Z])\s*([-+]?\d*\.?\d+)')
_LINENO = re.compile(r'^N\d+\s*')
NUMBERED_MAX = 64         # GRBL's line buffer holds 80 characters (70 in 0.9): only number lines that stay well under it
DEFAULT_DWELL = 0.3       # servo wait used when resuming a job that has no G4 of its own


def clean_lines(text):
    """Strip comments, blank lines and existing N line numbers; keep GRBL '$' commands as they are."""
    out = []
    for raw in text.replace('\r', '').split('\n'):
        line = _COMMENT.sub('', raw).strip()
        if line and not line.startswith('$'):
            line = _LINENO.sub('', line.upper())
        if line:
            out.append(line)
    return out


def _words(line):
    w = {}
    for k, v in _WORD.findall(line):
        w.setdefault(k, []).append(float(v))
    return w


def numbered(idx, line):
    """The line as sent: N<line number> in front, so GRBL's status reports which line it is executing (Ln:)."""
    if line.startswith('$'):
        return line
    s = f'N{idx + 1} {line}'
    return s if len(s) <= NUMBERED_MAX else line


def line_kinds(lines):
    """Per line: 1 = a move (takes planner blocks), 2 = G4 dwell (GRBL finishes every move before it answers), 0 = other."""
    kinds = bytearray(len(lines))
    for i, line in enumerate(lines):
        if line.startswith('$'):
            continue
        w = _words(line)
        g = w.get('G', [])
        if 4 in g:
            kinds[i] = 2
        elif any(k in w for k in 'XYZIJ') and not (10 in g or 92 in g):
            kinds[i] = 1
    return kinds


def job_dwell(lines):
    """The servo wait the job uses (its first G4 P…), for the pen lift when resuming."""
    for line in lines:
        if line.startswith('$'):
            continue
        w = _words(line)
        if 4 in w.get('G', []) and 'P' in w:
            return w['P'][0]
    return DEFAULT_DWELL


def walk(lines, pen_up=None, upto=None):
    """Run through the program; yields (index, state) after each line. The state dict is updated in place:
    x, y (end of the last move), feed, mode (G0–G3), units (20/21), absolute, down (pen), down_at (line where it went down)."""
    st = {'x': 0.0, 'y': 0.0, 'feed': None, 'mode': None, 'units': 21, 'absolute': True, 'down': False, 'down_at': None, 'ref': pen_up}
    n = len(lines) if upto is None else min(upto, len(lines))
    for i in range(n):
        line = lines[i]
        if not line.startswith('$'):
            w = _words(line)
            g = [int(v) for v in w.get('G', [])]
            m = [int(v) for v in w.get('M', [])]
            for c in g:
                if c in (0, 1, 2, 3):
                    st['mode'] = c
                elif c in (20, 21):
                    st['units'] = c
                elif c in (90, 91):
                    st['absolute'] = c == 90
            if 'F' in w:
                st['feed'] = w['F'][0]
            down = st['down']
            if 'S' in w and (3 in m or 4 in m or not m):
                s = w['S'][0]
                if st['ref'] is None:
                    st['ref'] = s        # no pen-up value given: the first S in the job lifts the pen
                down = abs(s - st['ref']) > 1e-6
            if 5 in m:
                down = False
            if down and not st['down']:
                st['down_at'] = i
            st['down'] = down
            if ('X' in w or 'Y' in w) and not any(c in (4, 10, 28, 30, 53, 92) for c in g):
                if st['absolute']:
                    st['x'], st['y'] = w['X'][0] if 'X' in w else st['x'], w['Y'][0] if 'Y' in w else st['y']
                else:
                    st['x'], st['y'] = st['x'] + (w['X'][0] if 'X' in w else 0.0), st['y'] + (w['Y'][0] if 'Y' in w else 0.0)
        yield i, st


def gcode_state(lines, upto, pen_up=None):
    """Modal state once lines[:upto] have run."""
    st = None
    for _, st in walk(lines, pen_up, upto):
        pass
    return st or next(walk([''], pen_up))[1]


def resume_point(lines, done, pen_up=None):
    """Where to pick up after lines[:done] were drawn: the start of the stroke in progress, so it is drawn whole
    (tracing a few millimetres twice doesn't show; a gap does)."""
    if done >= len(lines):
        return len(lines)
    st = gcode_state(lines, done, pen_up)
    return st['down_at'] if st['down'] and st['down_at'] is not None else done


def stroke_starts(lines, pen_up=None):
    """Line index of every pen-down: the places a job can be resumed from."""
    out, was = [], False
    for i, st in walk(lines, pen_up):
        if st['down'] and not was:
            out.append(i)
        was = st['down']
    return out


def resume_preamble(lines, start, pen_up=None, dwell=None):
    """G-code that puts the machine in the state the program has at lines[start]:
    pen up, travel to where that line starts, then restore units, feed and motion mode."""
    st = gcode_state(lines, start, pen_up)
    dwell = job_dwell(lines) if dwell is None else dwell
    pre = [f"G{st['units']}", 'G90', f"M3 S{st['ref']:g}" if st['ref'] is not None else 'M5']
    if dwell > 0:
        pre.append(f'G4 P{dwell:g}')
    pre.append(f"G0 X{st['x']:.3f} Y{st['y']:.3f}")
    if st['feed']:
        pre.append(f"G1 F{st['feed']:g}")
    if st['mode'] == 0:
        pre.append('G0')
    if not st['absolute']:
        pre.append('G91')
    return pre


def analyse(lines, pen_up=None):
    """Plotted moves for the preview, and cumulative drawn+travel length per line for progress."""
    moves, cum, total, px, py = [], [], 0.0, 0.0, 0.0
    for i, st in walk(lines, pen_up):
        x, y = st['x'], st['y']
        if (x, y) != (px, py):
            total += math.hypot(x - px, y - py)
            if not moves or moves[-1][1:3] != [round(px, 3), round(py, 3)]:
                moves.append([i, round(px, 3), round(py, 3), 0])
            moves.append([i, round(x, 3), round(y, 3), 1 if st['down'] else 0])
            px, py = x, y
        cum.append(total)
    return moves, cum, total


# ---------------------------------------------------------------------------
#  checkpoint: the current job on disk, so a plot survives a crash, a power cut or a restart
# ---------------------------------------------------------------------------
class JobStore:
    def __init__(self, folder):
        self.dir = folder
        self.lock = threading.Lock()
        self.rev = -1                     # newest snapshot written; older ones arriving late are dropped
        os.makedirs(folder, exist_ok=True)

    def _write(self, name, text):
        path = os.path.join(self.dir, name)
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)             # atomic: a power cut leaves the old file or the new one, never half of one

    def save_lines(self, lines):
        with self.lock:
            self._write('job.gcode', '\n'.join(lines) + '\n')

    def save_meta(self, meta):
        with self.lock:
            if meta['rev'] <= self.rev:
                return
            self.rev = meta['rev']
            self._write('job.json', json.dumps(meta))

    def load(self):
        try:
            with open(os.path.join(self.dir, 'job.json')) as f:
                meta = json.load(f)
            with open(os.path.join(self.dir, 'job.gcode')) as f:
                lines = [l for l in f.read().split('\n') if l]
        except (OSError, ValueError):
            return None, None
        if meta.get('total') != len(lines):
            return None, None
        self.rev = meta.get('rev', 0)
        return meta, lines

    def clear(self):
        with self.lock:
            for name in ('job.json', 'job.gcode'):
                try:
                    os.remove(os.path.join(self.dir, name))
                except OSError:
                    pass


# ---------------------------------------------------------------------------
#  machine: what this plotter is (bed, pen, speeds…). The bridge is the source of truth: every
#  browser and phone that connects reads the same profile from here and writes changes back.
# ---------------------------------------------------------------------------
PROFILE_KEYS = {'bedW': (1, 5000), 'bedH': (1, 5000), 'up': (0, 1000), 'down': (0, 1000), 'dwell': (0, 10), 'feed': (1, 100000),
                'travel': (1, 100000), 'parkX': (-5000, 5000), 'parkY': (-5000, 5000), 'decimals': (0, 6)}
PROFILE_FLAGS = ('travelG0', 'park', 'mirrorX')
PROFILE_TEXT = ('header', 'footer')


def clean_profile(p):
    """Only known settings, with sane types and ranges: the profile ends up in G-code."""
    if not isinstance(p, dict):
        raise ValueError('The machine settings must be an object')
    out = {}
    for k, (lo, hi) in PROFILE_KEYS.items():
        if k in p:
            try:
                v = float(p[k])
            except (TypeError, ValueError):
                raise ValueError(f'{k} must be a number')
            if not (lo <= v <= hi):          # also false for NaN
                raise ValueError(f'{k} must be between {lo:g} and {hi:g}')
            out[k] = int(v) if v == int(v) and k != 'dwell' else v
    for k in PROFILE_FLAGS:
        if k in p:
            out[k] = bool(p[k])
    for k in PROFILE_TEXT:
        if k in p:
            out[k] = str(p[k])[:4000]
    return out


class Conflict(Exception):
    def __init__(self, current):
        super().__init__('The settings changed on the bridge in the meantime')
        self.current = current


class MachineStore:
    """machine.json in the state folder: {id, name, rev, profile, updated}. `id` never changes, so a browser can
    recognise this plotter again when its IP address or name changes. `rev` counts saves, to catch two people editing at once."""

    def __init__(self, folder, name=None):
        self.path = os.path.join(folder, 'machine.json') if folder else None
        self.lock = threading.Lock()
        self.data = {'id': uuid.uuid4().hex[:12], 'name': name or socket.gethostname(), 'rev': 0, 'profile': None, 'updated': None}
        try:
            with open(self.path) as f:
                d = json.load(f)
            if isinstance(d, dict) and d.get('id'):
                self.data.update({k: d[k] for k in ('id', 'name', 'rev', 'profile', 'updated') if k in d})
        except (OSError, ValueError, TypeError):
            pass
        if name:
            self.data['name'] = name
        self._write()

    def _write(self):
        if not self.path:
            return
        tmp = self.path + '.tmp'
        try:
            with open(tmp, 'w') as f:
                json.dump(self.data, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except OSError as e:
            print(f'[err] Could not save the machine settings: {e}', flush=True)

    def get(self):
        with self.lock:
            return dict(self.data)

    def save(self, name, profile, base_rev):
        with self.lock:
            if base_rev is not None and self.data['profile'] is not None and int(base_rev) != self.data['rev']:
                raise Conflict(dict(self.data))
            if name is not None and str(name).strip():
                self.data['name'] = str(name).strip()[:60]
            if profile is not None:
                self.data['profile'] = clean_profile(profile)
            self.data['rev'] += 1
            self.data['updated'] = time.time()
            self._write()
            return dict(self.data)


# ---------------------------------------------------------------------------
#  GRBL connection + streamer
# ---------------------------------------------------------------------------
PLANNER_BLOCKS = 15       # moves GRBL 1.1 buffers on an Arduino; read from `$I` ([OPT:…,blocks,rx]) when reported
CHECKPOINT_EVERY = 2.0    # seconds between progress saves while plotting
STALL_AFTER = 15.0        # idle with lines unanswered this long = the controller lost them (a reset whose banner got lost)
RESUMABLE = ('stopped', 'failed', 'interrupted')


class Plotter:
    """Job progress has three counters: `next` (lines sent), `acked` (GRBL answered ok: parsed and queued) and
    `done` (known to be drawn). `done` is what gets saved and resumed from. It comes from the line number GRBL
    reports for the move it is executing (Ln:), from G4 dwells (answered only once every earlier move finished),
    and from the planner size (with more moves queued than fit in the planner, the oldest has finished)."""

    def __init__(self, port=None, baud=115200, autoconnect=True, store=None, machine=None):
        self.want_port, self.baud, self.autoconnect = port, baud, autoconnect
        self.machine = machine or MachineStore(None)
        self.grbl = {}                          # what the controller says about itself: version, options
        self.no_jog = False                     # this firmware rejected $J= (GRBL before 1.1): jog with plain moves
        self._last_jog = None
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.ser = None
        self.port = None
        self.state, self.alarm = 'Disconnected', None
        self.state_full = 'Disconnected'
        self.mpos = [0.0, 0.0, 0.0]
        self.wco = [0.0, 0.0, 0.0]
        self.settings = {}
        self.planner_blocks, self.rx_buffer = PLANNER_BLOCKS, RX_BUFFER
        self.inflight = collections.deque()     # (bytes, job line index | -1 for resume set-up | None for manual)
        self.manual = collections.deque()       # manual lines waiting to go out
        self.job = None
        self.job_seq = 0
        self.rev = 0                            # checkpoint snapshot counter
        self.log = collections.deque(maxlen=400)
        self.log_seq = 0
        self.banner_at = 0
        self.status_at = 0
        self.user_disconnected = False
        self.error = None
        self.store = store
        if store:
            self._restore()
            threading.Thread(target=self._saver, daemon=True).start()
        threading.Thread(target=self._supervisor, daemon=True).start()

    # ----- logging -----
    def say(self, kind, text):
        with self.lock:
            self.log_seq += 1
            self.log.append({'seq': self.log_seq, 't': round(time.time(), 2), 'k': kind, 'm': text})
        if kind in ('err', 'sys'):
            print(f'[{kind}] {text}', flush=True)

    # ----- connection -----
    def connect(self, port=None, baud=None):
        with self.lock:
            if self.ser:
                self._close('Reconnecting')
            port = port or self.want_port or guess_port()
            if not port:
                raise RuntimeError('No serial port found — is the plotter plugged in?')
            baud = int(baud or self.baud)
            self.state = 'Connecting'
        try:
            ser = SerialPort(port, baud)
        except Exception as e:
            with self.lock:
                self.state = 'Disconnected'
                self.error = f'Could not open {port}: {e}'
            raise RuntimeError(self.error)
        with self.lock:
            self.ser, self.port, self.baud, self.want_port = ser, port, baud, port
            self.user_disconnected, self.error, self.alarm = False, None, None
            self.inflight.clear(); self.manual.clear()
            self.banner_at = 0
        self.say('sys', f'Opened {port} at {baud} baud')
        threading.Thread(target=self._reader, args=(ser,), daemon=True).start()
        threading.Thread(target=self._poller, args=(ser,), daemon=True).start()
        threading.Thread(target=self._sender, args=(ser,), daemon=True).start()
        # Opening the port resets most Arduino boards; wait for the GRBL banner, else nudge it.
        t0 = time.time()
        while time.time() - t0 < 2.5 and not self.banner_at:
            time.sleep(0.05)
        if not self.banner_at:
            self._raw(b'\r\n\r\n')
            time.sleep(0.3)
        self.inflight.clear()
        self.queue('$$')
        self.queue('$I')
        return True

    def disconnect(self):
        with self.lock:
            self.user_disconnected = True
            self._close('Disconnected by user')

    def _close(self, why):
        ser, self.ser = self.ser, None
        if ser:
            ser.close()
            self.say('sys', why)
        self.state = 'Disconnected'
        self.inflight.clear(); self.manual.clear()
        if self.job and self.job['running']:
            self._end_job(f'Connection lost: {why}')
        self.cond.notify_all()

    def _supervisor(self):
        while True:
            time.sleep(3)
            if self.ser or self.user_disconnected or not self.autoconnect:
                continue
            if (self.want_port and os.path.exists(self.want_port)) or (not self.want_port and guess_port()):
                try:
                    self.connect()
                except Exception as e:
                    self.say('err', str(e))

    def _raw(self, data):
        ser = self.ser
        if ser:
            try:
                ser.write(data)
            except Exception as e:
                with self.lock:
                    if self.ser is ser:
                        self._close(f'Write failed: {e}')

    # ----- threads -----
    def _poller(self, ser):
        while self.ser is ser:
            self._raw(b'?')
            time.sleep(STATUS_EVERY)

    def _reader(self, ser):
        buf = b''
        while self.ser is ser:
            try:
                data = ser.read(0.1)
            except Exception as e:
                with self.lock:
                    if self.ser is ser:
                        self._close(f'Plotter disconnected ({e})')
                return
            if not data:
                continue
            buf += data
            while b'\n' in buf:
                line, buf = buf.split(b'\n', 1)
                text = line.decode('ascii', 'replace').strip()
                if text:
                    self._handle(text)

    def _sender(self, ser):
        while True:
            with self.cond:
                if self.ser is not ser:
                    return
                sent = False
                used = sum(len(b) for b, _ in self.inflight)
                j = self.job
                item = None
                if self.manual:
                    item = (self.manual[0], None)
                elif j and j['running'] and not j['stopping']:
                    if j['pre_next'] < len(j['pre']):
                        item = (j['pre'][j['pre_next']], -1)
                    elif j['next'] < len(j['lines']):
                        item = (numbered(j['next'], j['lines'][j['next']]), j['next'])
                if item:
                    b = (item[0] + '\n').encode()
                    if used + len(b) <= self.rx_buffer or not self.inflight:
                        if item[1] is None:
                            self.manual.popleft()
                        elif item[1] < 0:
                            j['pre_next'] += 1
                        else:
                            j['next'] += 1
                        self.inflight.append((b, item[1]))
                        self._raw(b)
                        sent = True
                if not sent:
                    self.cond.wait(0.5)

    def _saver(self):
        while True:
            time.sleep(CHECKPOINT_EVERY)
            with self.lock:
                j = self.job
                meta = self._meta(j) if j and j['dirty'] else None
            if meta:
                self._store_meta(meta)

    # ----- responses -----
    def _handle(self, text):
        with self.cond:
            if text.startswith('<'):
                self._status(text[1:].rstrip('>'))
                return
            if text == 'ok' or text.startswith('error'):
                b, idx = self.inflight.popleft() if self.inflight else (b'', None)
                j = self.job
                if text.startswith('error'):
                    sent = b.decode().strip()
                    msg = f'{text} on "{sent}"' + (f' (line {idx + 1})' if idx is not None and idx >= 0 else '')
                    self.say('err', msg)
                    if idx is None and sent.startswith('$J=') and not self.no_jog:   # no jog command in this firmware: do it with a plain move
                        self.no_jog = True
                        self.say('sys', 'This GRBL has no $J jog command (it is older than 1.1) — jogging with plain moves instead')
                        if self._last_jog:
                            threading.Thread(target=self.jog, args=self._last_jog, daemon=True).start()
                    if idx is not None and j and j['running']:
                        self._abort_locked(f'GRBL rejected a line: {msg}')
                elif idx is not None and idx >= 0 and j:
                    self._acked(j, idx)
                elif idx is None:
                    self.say('rx', 'ok')
                self.cond.notify_all()
                return
            if text.startswith('Grbl') or text.startswith('grblHAL'):
                self.banner_at = time.time()      # the position is unknown until the next status report
                self.inflight.clear()
                self.state = 'Idle'
                self.say('rx', text)
                if self.job and self.job['running'] and not self.job['stopping']:
                    self._end_job('The controller reset during the plot')
                self.cond.notify_all()
                return
            if text.startswith('ALARM'):
                self.alarm = text
                self.state = 'Alarm'
                self.inflight.clear()
                self.say('err', text + ' — unlock ($X) or home ($H) before continuing')
                if self.job and self.job['running'] and not self.job['stopping']:
                    self._end_job(f'Plotter alarm ({text})')
                self.cond.notify_all()
                return
            m = re.match(r'^\$(\d+)=([-\d.]+)', text)
            if m:
                self.settings[int(m.group(1))] = float(m.group(2))
                return
            m = re.match(r'^\[VER:([^:\]]*)', text)
            if m:
                self.grbl['version'] = m.group(1)
            m = re.match(r'^\[OPT:([^,]*),', text)
            if m:
                self.grbl['options'] = m.group(1)
            m = re.match(r'^\[OPT:[^,]*,(\d+),(\d+)', text)
            if m:   # GRBL 1.1 / grblHAL build options: planner blocks and serial buffer size
                self.planner_blocks, self.rx_buffer = int(m.group(1)), max(64, min(int(m.group(2)), 1024) - 1)
            self.say('rx', text)

    def _acked(self, j, idx):
        j['acked'] = idx + 1
        j['last_ack'] = time.time()
        kind = j['kinds'][idx]
        if kind == 2:                     # a dwell is answered once everything before it has run
            j['recent'].clear()
            self._advance(j, idx + 1)
        elif kind == 1:
            j['recent'].append(idx)
            if len(j['recent']) > self.planner_blocks:
                self._advance(j, j['recent'].popleft() + 1)
        if j['acked'] >= len(j['lines']):
            j['all_acked'] = time.time()

    def _advance(self, j, done):
        if done > j['done']:
            j['done'] = done
            j['dirty'] = True

    def _status(self, body):
        parts = re.split(r'[|]', body) if '|' in body else re.split(r',(?=[A-Za-z])', body)
        self.state_full = parts[0]
        self.state = parts[0].split(':')[0]
        self.status_at = time.time()
        if self.state != 'Alarm':
            self.alarm = None
        wpos, ln = None, None
        for p in parts[1:]:
            k, _, v = p.partition(':')
            try:
                vals = [float(n) for n in v.split(',')]
            except ValueError:
                continue
            if k == 'MPos': self.mpos = vals[:3]
            elif k == 'WPos': wpos = vals[:3]
            elif k == 'WCO': self.wco = vals[:3]
            elif k == 'Ln': ln = int(vals[0])
        if wpos is not None:
            self.mpos = [a + b for a, b in zip(wpos, self.wco)]
        j = self.job
        if j and j['running']:
            j['pos'] = [round(a - b, 3) for a, b in zip(self.mpos[:2], self.wco[:2])]
            if ln and j['pre_next'] >= len(j['pre']) and ln - 1 <= j['acked']:
                self._advance(j, ln - 1)  # Ln = the line GRBL is executing: everything before it is drawn
            if j['all_acked'] and self.state == 'Idle' and time.time() - j['all_acked'] > 0.3:
                self._end_job(None)
            elif self.state == 'Idle' and self.inflight and time.time() - j['last_ack'] > STALL_AFTER:
                self._end_job('The plotter stopped answering mid-plot (it may have reset)')

    # ----- jobs -----
    def _new_job(self, lines, name, pen_up, meta=None, dwell=None):
        moves, cum, total = analyse(lines, pen_up)
        now = time.time()
        return {'id': self.job_seq, 'name': name, 'meta': meta or {}, 'lines': lines, 'kinds': line_kinds(lines),
                'pen_up': pen_up, 'dwell': job_dwell(lines) if dwell is None else dwell,
                'pre': [], 'pre_next': 0, 'next': 0, 'acked': 0, 'done': 0, 'done0': 0, 'recent': collections.deque(),
                'running': True, 'stopping': False, 'paused': False, 'state': 'running', 'error': None,
                'started': now, 'ended': None, 'run_time': 0.0, 't_run': now, 'all_acked': None, 'last_ack': now,
                'moves': moves, 'cum': cum, 'length': total, 'pos': None, 'resume_at': None, 'resume_from': 0,
                'strokes': None, 'dirty': False}

    def run(self, gcode, name='Plot', pen_up=None, meta=None, dwell=None):
        lines = clean_lines(gcode)
        if not lines:
            raise RuntimeError('The G-code is empty')
        with self.cond:
            if not self.ser:
                raise RuntimeError('The plotter is not connected')
            if self.job and self.job['running']:
                raise RuntimeError('A plot is already running')
            if self.state == 'Alarm':
                raise RuntimeError('The plotter is in alarm — unlock or home it first')
            self.job_seq += 1
            self.job = self._new_job(lines, name, pen_up, meta, dwell)
            if self.store:
                try:
                    self.store.save_lines(lines)
                except OSError as e:
                    self.say('err', f'Could not save the job for recovery: {e}')
            self._save_now()
            self.say('sys', f'Started "{name}" — {len(lines)} lines')
            self.cond.notify_all()
        return self.job['id']

    def resume_job(self, start=None):
        """Continue a stopped or interrupted job from line `start` (default: the start of the stroke it was on)."""
        with self.cond:
            j = self.job
            if not j:
                raise RuntimeError('There is no plot to resume')
            if j['running']:
                raise RuntimeError('The plot is already running')
            if j['state'] == 'finished':
                raise RuntimeError('That plot has already finished')
            if not self.ser:
                raise RuntimeError('The plotter is not connected')
            if self.state == 'Alarm':
                raise RuntimeError('The plotter is in alarm — unlock or home it first')
            n = len(j['lines'])
            start = j['resume_at'] if start is None else int(start)
            start = max(0, min(start if start is not None else j['done'], n - 1))
            j['pre'] = resume_preamble(j['lines'], start, j['pen_up'], j['dwell'])
            j.update(pre_next=0, next=start, acked=start, done=start, done0=start, resume_from=start, running=True,
                     stopping=False, paused=False, error=None, state='running', all_acked=None, ended=None, t_run=time.time(), last_ack=time.time())
            j['recent'].clear()
            self._save_now()
            self.say('sys', f'Resuming "{j["name"]}" from line {start + 1} of {n}')
            self.cond.notify_all()
            return j['id']

    def discard_job(self):
        with self.lock:
            if self.job and self.job['running']:
                raise RuntimeError('The plot is running — stop it first')
            self.job = None
            if self.store:
                self.store.clear()

    def _end_job(self, error, state=None):
        j = self.job
        if not j or not j['running']:
            return
        now = time.time()
        j['run_time'] += now - j['t_run']
        j['running'], j['ended'], j['error'], j['paused'] = False, now, error, False
        n = len(j['lines'])
        if error:
            j['state'] = state or 'interrupted'
            j['resume_at'] = resume_point(j['lines'], j['done'], j['pen_up'])
            self.say('err', f'"{j["name"]}" stopped: {error} — {j["done"]} of {n} lines drawn; it can resume from line {j["resume_at"] + 1}')
        else:
            j['state'], j['acked'], j['done'], j['resume_at'] = 'finished', n, n, None
            self.say('sys', f'Finished "{j["name"]}" in {fmt_dur(j["run_time"])}')
        self._save_now()

    # ----- checkpoint -----
    def _meta(self, j):
        self.rev += 1
        j['dirty'] = False
        return {'version': 1, 'rev': self.rev, 'id': j['id'], 'name': j['name'], 'meta': j['meta'], 'pen_up': j['pen_up'],
                'dwell': j['dwell'], 'total': len(j['lines']), 'done': j['done'], 'state': j['state'], 'error': j['error'],
                'started': j['started'], 'ended': j['ended'], 'run_time': j['run_time'] + ((time.time() - j['t_run']) if j['running'] else 0),
                'pos': j['pos'], 'resume_at': j['resume_at'], 'resume_from': j['resume_from'], 'saved': time.time()}

    def _store_meta(self, meta):
        try:
            self.store.save_meta(meta)
        except OSError as e:
            self.say('err', f'Could not save progress: {e}')

    def _save_now(self):
        if self.store and self.job:
            self._store_meta(self._meta(self.job))

    def _restore(self):
        meta, lines = self.store.load()
        if not meta:
            return
        self.job_seq = int(meta.get('id', 0))
        self.rev = int(meta.get('rev', 0))
        j = self._new_job(lines, meta.get('name') or 'Plot', meta.get('pen_up'), meta.get('meta'), meta.get('dwell'))
        state = meta.get('state', 'interrupted')
        done = max(0, min(int(meta.get('done', 0)), len(lines)))
        j.update(running=False, done=done, acked=done, state=state, error=meta.get('error'), started=meta.get('started') or j['started'],
                 ended=meta.get('ended') or meta.get('saved'), run_time=meta.get('run_time') or 0.0, pos=meta.get('pos'),
                 resume_from=meta.get('resume_from') or 0)
        if state == 'running':            # it was plotting when the bridge went away
            j['state'] = 'interrupted'
            j['error'] = 'The bridge stopped while plotting (power cut, crash or restart)'
        if j['state'] in RESUMABLE:
            j['resume_at'] = resume_point(lines, done, j['pen_up'])
            self.say('sys', f'Found an unfinished plot "{j["name"]}": {done} of {len(lines)} lines drawn — resume it from the monitor or Plot Studio')
        self.job = j
        self._save_now()

    def pause(self):
        self._raw(b'!')
        with self.lock:
            if self.job and self.job['running']:
                self.job['paused'] = True
        self.say('tx', 'Feed hold (!)')

    def resume(self):
        self._raw(b'~')
        with self.lock:
            if self.job:
                self.job['paused'] = False
        self.say('tx', 'Resume (~)')

    def _abort_locked(self, reason):
        if self.job and self.job['running']:
            self.job['stopping'] = True
        threading.Thread(target=self.stop, args=(reason, None, 'failed'), daemon=True).start()

    def stop(self, reason='Stopped by user', pen_up=None, state='stopped'):
        """Feed hold, wait for the machine to come to rest (keeps position), soft reset, lift the pen."""
        with self.cond:
            if self.job and self.job['running']:
                self.job['stopping'] = True
            pen_up = pen_up or (self.job and self.job.get('pen_up') is not None and f"M3 S{self.job['pen_up']:g}") or None
        self._raw(b'!')
        t0 = time.time()
        while time.time() - t0 < 4 and self.state not in ('Idle', 'Alarm', 'Disconnected') and self.state_full != 'Hold:0':
            time.sleep(0.05)
            if self.state_full == 'Hold' and time.time() - t0 > 0.6:   # GRBL 0.9 has no Hold:0/Hold:1
                break
        time.sleep(0.15)
        with self.cond:
            self.manual.clear()
            self._end_job(reason, state)
            self.banner_at = 0
        self._raw(b'\x18')
        t0 = time.time()
        while time.time() - t0 < 3 and not self.banner_at:
            time.sleep(0.05)
        with self.cond:
            self.inflight.clear()
            if pen_up and self.state != 'Alarm':
                self.manual.append(pen_up)
            self.cond.notify_all()
        self.say('sys', 'Stopped and reset' + (f' — pen lifted ({pen_up})' if pen_up and self.state != 'Alarm' else ''))

    def queue(self, line):
        line = line.strip()
        if not line:
            return
        with self.cond:
            if not self.ser:
                raise RuntimeError('The plotter is not connected')
            if self.job and self.job['running'] and not line.startswith('$J='):
                raise RuntimeError('A plot is running — wait for it to finish or stop it')
            self.manual.append(line)
            if line not in ('$$', '$I'):
                self.say('tx', line)
            self.cond.notify_all()

    def jog(self, dx, dy, feed):
        """Move the pen by dx, dy. GRBL 1.1 has jog commands ($J=, cancellable, never leaves a mode behind); older firmware
        reads `$J=` as a setting and answers "Bad number format", so there it is a plain absolute move, kept inside the bed."""
        self._last_jog = (dx, dy, feed)
        version = self.grbl.get('version') or ''
        if version and not version.startswith('0.') and not self.no_jog:
            return self.queue(f'$J=G21G91X{dx:g}Y{dy:g}F{feed:g}')
        with self.lock:
            wx, wy = (self.settings.get(130), self.settings.get(131))
            px, py = self.mpos[0] - self.wco[0], self.mpos[1] - self.wco[1]
        prof = self.machine.get().get('profile') or {}
        W, H = wx or prof.get('bedW') or 310.0, wy or prof.get('bedH') or 210.0
        x, y = min(max(px + dx, 0.0), W), min(max(py + dy, 0.0), H)
        self.queue(f'G21 G90 G1 X{x:.3f} Y{y:.3f} F{feed:g}')

    def set_origin(self, x=0.0, y=0.0):
        """Tell GRBL the pen is at work position x, y. G10 L20 stores it in G54, which survives resets."""
        self.queue(f'G10 L20 P1 X{float(x):.3f} Y{float(y):.3f}')

    # ----- views -----
    def _job_view(self, j):
        n = len(j['lines'])
        at = lambda d: (j['cum'][d - 1] / j['length']) if (j['length'] and d) else d / n
        frac = 1.0 if j['state'] == 'finished' else at(j['done'])
        now = time.time()
        elapsed = j['run_time'] + (now - j['t_run'] if j['running'] else 0)
        eta, ran, gained = None, now - j['t_run'], frac - at(j['done0'])
        if j['running'] and ran > 5 and gained > 0.005:
            eta = ran * (1 - frac) / gained
        return {'id': j['id'], 'name': j['name'], 'meta': j['meta'], 'running': j['running'], 'paused': j['paused'],
                'stopping': j['stopping'], 'state': j['state'], 'error': j['error'], 'total': n, 'done': j['done'],
                'sent': j['done'], 'acked': j['acked'], 'queued': j['next'], 'progress': round(frac, 4),
                'elapsed': round(elapsed, 1), 'eta': round(eta, 1) if eta is not None else None,
                'started': j['started'], 'ended': j['ended'], 'pos': j['pos'], 'resume_from': j['resume_from'],
                'resumable': not j['running'] and j['state'] in RESUMABLE and (j['resume_at'] or 0) < n,
                'resume_at': j['resume_at']}

    def status(self, since=None):
        with self.lock:
            wpos = [round(a - b, 3) for a, b in zip(self.mpos, self.wco)]
            st = {'bridge': VERSION, 'host': socket.gethostname(), 'connected': self.ser is not None,
                  'port': self.port, 'baud': self.baud, 'state': self.state, 'alarm': self.alarm,
                  'pos': wpos, 'pos_fresh': self.status_at > self.banner_at, 'job': self._job_view(self.job) if self.job else None, 'error': self.error, 'seq': self.log_seq,
                  'homing': self.settings.get(22) == 1, 'resume': True, 'machine_rev': self.machine.data['rev'],
                  'grbl': {**self.grbl, 'settings': {str(k): v for k, v in self.settings.items() if k in (10, 20, 21, 22, 30, 31, 32, 110, 111, 130, 131)}}}
            if 130 in self.settings and 131 in self.settings:
                st['work'] = [self.settings[130], self.settings[131]]
            if since is not None:
                st['log'] = [e for e in self.log if e['seq'] > since]
            return st

    def job_detail(self, with_gcode=False):
        with self.lock:
            j = self.job
            if not j:
                return {'job': None}
            if j['strokes'] is None:
                j['strokes'] = stroke_starts(j['lines'], j['pen_up'])
            out = {'id': j['id'], 'name': j['name'], 'total': len(j['lines']), 'moves': j['moves'], 'strokes': j['strokes'],
                   'done': j['done'], 'state': j['state'], 'resume_at': j['resume_at'], 'pen_up': j['pen_up'], 'meta': j['meta']}
            if with_gcode:
                out['lines'] = j['lines']
            return {'job': out}


def fmt_dur(s):
    s = int(s)
    return f'{s // 3600} h {s % 3600 // 60} min' if s >= 3600 else f'{s // 60} min {s % 60} s'


# ---------------------------------------------------------------------------
#  HTTP API
# ---------------------------------------------------------------------------
def find_file(name):
    """A page next to bridge.py (the installed copy), else in the folder above (running from a clone)."""
    return next((p for p in (os.path.join(HERE, name), os.path.join(os.path.dirname(HERE), name)) if os.path.exists(p)), None)


class Handler(BaseHTTPRequestHandler):
    server_version = f'PlotterBridge/{VERSION}'
    plotter: Plotter = None
    token = None
    studio_url = STUDIO_URL

    def log_message(self, *a):
        pass

    def _cors(self):
        origin = self.headers.get('Origin')
        self.send_header('Access-Control-Allow-Origin', origin or '*')
        self.send_header('Vary', 'Origin')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Bridge-Token')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Private-Network', 'true')   # Chrome private-network preflights

    def _send(self, code, body, ctype='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _authed(self, q):
        if not self.token:
            return True
        given = self.headers.get('X-Bridge-Token') or (q.get('token') or [''])[0]
        return given == self.token

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path in ('/', '/monitor'):
            return self._file('monitor.html')
        if u.path in ('/studio', '/studio/'):
            if find_file('studio.html'):
                return self._file('studio.html')
            self.send_response(302)    # the studio is not kept here: it lives at the hosted address and always is the newest
            self.send_header('Location', self.studio_url)
            self.send_header('Content-Length', '0')
            return self.end_headers()
        if u.path == '/api/info':
            m = self.plotter.machine.get()
            return self._send(200, {'name': 'plotter-bridge', 'version': VERSION, 'host': socket.gethostname(), 'auth': bool(self.token),
                                    'id': m['id'], 'machine': m['name'], 'studio': self.studio_url, 'studio_local': bool(find_file('studio.html'))})
        if not u.path.startswith('/api/'):
            return self._send(404, {'error': 'Not found'})
        if not self._authed(q):
            return self._send(401, {'error': 'This bridge needs an access token'})
        if u.path == '/api/status':
            since = q.get('since', [None])[0]
            try:
                since = int(float(since)) if since is not None else None
            except ValueError:
                since = None
            return self._send(200, self.plotter.status(since))
        if u.path == '/api/job':
            return self._send(200, self.plotter.job_detail(with_gcode=bool(q.get('gcode'))))
        if u.path == '/api/machine':
            return self._send(200, {'machine': self.plotter.machine.get()})
        if u.path == '/api/ports':
            return self._send(200, {'ports': list_ports(), 'current': self.plotter.port})
        self._send(404, {'error': 'Unknown endpoint'})

    def do_POST(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if not self._authed(q):
            return self._send(401, {'error': 'This bridge needs an access token'})
        try:
            n = int(self.headers.get('Content-Length') or 0)
            if n > 64 * 1024 * 1024:
                return self._send(413, {'error': 'Job too large'})
            body = json.loads(self.rfile.read(n) or b'{}') if n else {}
        except Exception:
            return self._send(400, {'error': 'Bad JSON'})
        P, cmd = self.plotter, u.path[len('/api/'):]
        try:
            if cmd == 'status':
                return self._send(200, P.status(None))
            if cmd == 'job':
                return self._send(200, P.job_detail(with_gcode=bool(body.get('gcode'))))
            if cmd == 'machine':
                try:
                    return self._send(200, {'ok': True, 'machine': P.machine.save(body.get('name'), body.get('profile'), body.get('baseRev'))})
                except Conflict as c:
                    return self._send(200, {'error': str(c), 'conflict': True, 'machine': c.current})
                except ValueError as e:
                    return self._send(200, {'error': str(e)})
            if cmd == 'connect':
                P.connect(body.get('port'), body.get('baud'))
            elif cmd == 'disconnect':
                P.disconnect()
            elif cmd == 'run':
                pen_up, dwell = body.get('penUp'), body.get('dwell')
                meta = body.get('meta') if isinstance(body.get('meta'), dict) else None
                jid = P.run(body.get('gcode', ''), body.get('name') or 'Plot', float(pen_up) if pen_up not in (None, '') else None,
                            meta, float(dwell) if dwell not in (None, '') else None)
                return self._send(200, {'ok': True, 'id': jid})
            elif cmd == 'job/resume':
                start = body.get('from')
                return self._send(200, {'ok': True, 'id': P.resume_job(int(start) if start not in (None, '') else None)})
            elif cmd == 'job/discard':
                P.discard_job()
            elif cmd == 'origin':
                if P.job and P.job['running']:
                    raise RuntimeError('A plot is running')
                P.set_origin(body.get('x', 0), body.get('y', 0))
            elif cmd == 'pause':
                P.pause()
            elif cmd == 'resume':
                P.resume()
            elif cmd == 'stop':
                P.stop('Stopped by user', body.get('penUp'))
            elif cmd == 'send':
                for line in str(body.get('line', '')).split('\n'):
                    P.queue(line)
            elif cmd == 'unlock':
                P.queue('$X')
            elif cmd == 'home':
                P.queue('$H')
            elif cmd == 'jog':
                if P.job and P.job['running']:
                    raise RuntimeError('A plot is running')
                dx, dy, f = float(body.get('x', 0)), float(body.get('y', 0)), float(body.get('feed', 3000))
                P.jog(dx, dy, f)
            elif cmd == 'jogcancel':
                P._raw(b'\x85')
            else:
                return self._send(404, {'error': 'Unknown endpoint'})
            return self._send(200, {'ok': True})
        except RuntimeError as e:
            return self._send(200, {'error': str(e)})
        except Exception as e:
            return self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def _file(self, name):
        path = find_file(name)
        if not path:
            return self._send(404, f'{name} was not found next to bridge.py or in the folder above'.encode(), 'text/plain')
        with open(path, 'rb') as f:
            self._send(200, f.read(), 'text/html; charset=utf-8')


def main():
    ap = argparse.ArgumentParser(description='Stream G-code to a GRBL pen plotter and monitor it over the network.')
    ap.add_argument('--port', default=os.environ.get('PLOTTER_PORT'), help='serial port (default: auto-detect)')
    ap.add_argument('--baud', type=int, default=int(os.environ.get('PLOTTER_BAUD', 115200)))
    ap.add_argument('--host', default=os.environ.get('BRIDGE_HOST', '0.0.0.0'), help='address to listen on (default: all)')
    ap.add_argument('--http-port', type=int, default=int(os.environ.get('BRIDGE_PORT', 8080)))
    ap.add_argument('--token', default=os.environ.get('BRIDGE_TOKEN'), help='require this token for the API')
    ap.add_argument('--no-autoconnect', action='store_true', help='only connect when asked from the web page')
    ap.add_argument('--state', default=os.environ.get('BRIDGE_STATE', os.path.join(os.path.expanduser('~'), '.plotter-bridge')),
                    help='folder for the job checkpoint used to resume after a crash (default: ~/.plotter-bridge)')
    ap.add_argument('--cert', default=os.environ.get('BRIDGE_CERT'), help='TLS certificate (PEM): serve https directly')
    ap.add_argument('--key', default=os.environ.get('BRIDGE_KEY'), help='its private key (PEM); omit if the certificate file holds it too')
    ap.add_argument('--studio-url', default=os.environ.get('BRIDGE_STUDIO_URL', STUDIO_URL), help='where Plot Studio is hosted (default: %(default)s)')
    ap.add_argument('--name', default=os.environ.get('BRIDGE_NAME'), help='name of this plotter in Plot Studio (default: the computer’s name)')
    a = ap.parse_args()

    try:
        store = JobStore(a.state)
    except OSError as e:
        print(f'[err] Cannot use {a.state} for job recovery ({e}) — plots will not survive a restart', flush=True)
        store = None
    plotter = Plotter(a.port, a.baud, autoconnect=not a.no_autoconnect, store=store,
                      machine=MachineStore(a.state if store else None, a.name))
    Handler.plotter, Handler.token, Handler.studio_url = plotter, a.token or None, a.studio_url
    if not a.no_autoconnect:
        try:
            plotter.connect()
        except Exception as e:
            print(f'[sys] {e} — will keep looking', flush=True)
    srv = ThreadingHTTPServer((a.host, a.http_port), Handler)
    srv.daemon_threads = True
    scheme = 'http'
    if a.cert:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(a.cert, a.key or None)
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        scheme = 'https'
    host = socket.gethostname()
    print(f'[sys] Plotter Bridge {VERSION} — monitor: {scheme}://{host}.local:{a.http_port}/  add it in Plot Studio ({a.studio_url}) with that address'
          + ('  (token required)' if a.token else ''), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
