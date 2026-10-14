#!/usr/bin/env python3
"""
Plotter Bridge — streams G-code to a GRBL pen plotter over USB serial and lets
Plot Studio (or any browser) send jobs and monitor them over the network.

  python3 bridge.py                      # auto-detect the plotter, serve on :8080
  python3 bridge.py --port /dev/ttyUSB0 --baud 115200 --token s3cret

Open http://<this-computer>:8080/ for the live monitor and
http://<this-computer>:8080/studio for Plot Studio talking to this bridge.

Only the Python 3 standard library is needed on Linux and macOS. On Windows,
install pyserial (pip install pyserial); it is also used on Linux/macOS when present.
"""
import argparse, collections, glob, json, math, os, re, select, socket, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

VERSION = '1.0.0'
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


def clean_lines(text):
    """Strip comments and blank lines; keep GRBL '$' commands as they are."""
    out = []
    for raw in text.replace('\r', '').split('\n'):
        line = _COMMENT.sub('', raw).strip()
        if line:
            out.append(line if line.startswith('$') else line.upper())
    return out


def analyse(lines, pen_up=None):
    """Plotted moves for the preview, and cumulative drawn+travel length per line for progress."""
    x = y = 0.0
    absolute, down, first_s = True, False, None
    moves, cum, total = [], [], 0.0
    for i, line in enumerate(lines):
        if line.startswith('$'):
            cum.append(total)
            continue
        words = dict()
        for k, v in _WORD.findall(line):
            words.setdefault(k, []).append(float(v))
        g = [int(v) for v in words.get('G', [])]
        m = [int(v) for v in words.get('M', [])]
        if 90 in g: absolute = True
        if 91 in g: absolute = False
        if 'S' in words and (3 in m or 4 in m or not m):
            s = words['S'][0]
            if first_s is None: first_s = s
            ref = pen_up if pen_up is not None else first_s
            down = abs(s - ref) > 1e-6
        if 5 in m:
            down = False
        if ('X' in words or 'Y' in words) and not (4 in g or 92 in g or 10 in g or 28 in g or 30 in g or 53 in g):
            nx = words['X'][0] if 'X' in words else (x if absolute else 0.0)
            ny = words['Y'][0] if 'Y' in words else (y if absolute else 0.0)
            if not absolute:
                nx, ny = x + nx, y + ny
            total += math.hypot(nx - x, ny - y)
            if not moves or moves[-1][1:3] != [round(x, 3), round(y, 3)]:
                moves.append([i, round(x, 3), round(y, 3), 0])
            moves.append([i, round(nx, 3), round(ny, 3), 1 if down else 0])
            x, y = nx, ny
        cum.append(total)
    return moves, cum, total


# ---------------------------------------------------------------------------
#  GRBL connection + streamer
# ---------------------------------------------------------------------------
class Plotter:
    def __init__(self, port=None, baud=115200, autoconnect=True):
        self.want_port, self.baud, self.autoconnect = port, baud, autoconnect
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.ser = None
        self.port = None
        self.state, self.alarm = 'Disconnected', None
        self.state_full = 'Disconnected'
        self.mpos = [0.0, 0.0, 0.0]
        self.wco = [0.0, 0.0, 0.0]
        self.settings = {}
        self.inflight = collections.deque()     # (bytes, job line index or None)
        self.manual = collections.deque()       # manual lines waiting to go out
        self.job = None
        self.job_seq = 0
        self.log = collections.deque(maxlen=400)
        self.log_seq = 0
        self.banner_at = 0
        self.user_disconnected = False
        self.error = None
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
                if self.manual:
                    b = (self.manual[0] + '\n').encode()
                    if used + len(b) <= RX_BUFFER or not self.inflight:
                        self.manual.popleft()
                        self.inflight.append((b, None))
                        self._raw(b)
                        sent = True
                elif self.job and self.job['running'] and not self.job['stopping'] and self.job['next'] < len(self.job['lines']):
                    j = self.job
                    b = (j['lines'][j['next']] + '\n').encode()
                    if used + len(b) <= RX_BUFFER or not self.inflight:
                        self.inflight.append((b, j['next']))
                        j['next'] += 1
                        self._raw(b)
                        sent = True
                if not sent:
                    self.cond.wait(0.5)

    # ----- responses -----
    def _handle(self, text):
        with self.cond:
            if text.startswith('<'):
                self._status(text[1:].rstrip('>'))
                return
            if text == 'ok' or text.startswith('error'):
                b, idx = self.inflight.popleft() if self.inflight else (b'', None)
                if text.startswith('error'):
                    sent = b.decode().strip()
                    msg = f'{text} on "{sent}"' + (f' (line {idx + 1})' if idx is not None else '')
                    self.say('err', msg)
                    if idx is not None and self.job and self.job['running']:
                        self._abort_locked(f'GRBL rejected a line: {msg}')
                elif idx is not None and self.job:
                    self.job['acked'] = idx + 1
                    if self.job['acked'] >= len(self.job['lines']):
                        self.job['all_acked'] = time.time()
                elif idx is None:
                    self.say('rx', 'ok')
                self.cond.notify_all()
                return
            if text.startswith('Grbl') or text.startswith('grblHAL'):
                self.banner_at = time.time()
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
            self.say('rx', text)

    def _status(self, body):
        parts = re.split(r'[|]', body) if '|' in body else re.split(r',(?=[A-Za-z])', body)
        self.state_full = parts[0]
        self.state = parts[0].split(':')[0]
        if self.state != 'Alarm':
            self.alarm = None
        wpos = None
        for p in parts[1:]:
            k, _, v = p.partition(':')
            try:
                vals = [float(n) for n in v.split(',')]
            except ValueError:
                continue
            if k == 'MPos': self.mpos = vals[:3]
            elif k == 'WPos': wpos = vals[:3]
            elif k == 'WCO': self.wco = vals[:3]
        if wpos is not None:
            self.mpos = [a + b for a, b in zip(wpos, self.wco)]
        j = self.job
        if j and j['running'] and j['all_acked'] and self.state == 'Idle' and time.time() - j['all_acked'] > 0.3:
            self._end_job(None)

    # ----- jobs -----
    def run(self, gcode, name='Plot', pen_up=None):
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
            moves, cum, total = analyse(lines, pen_up)
            self.job_seq += 1
            self.job = {'id': self.job_seq, 'name': name, 'lines': lines, 'next': 0, 'acked': 0, 'running': True,
                        'stopping': False, 'paused': False, 'error': None, 'started': time.time(), 'ended': None,
                        'all_acked': None, 'moves': moves, 'cum': cum, 'length': total, 'pen_up': pen_up}
            self.say('sys', f'Started "{name}" — {len(lines)} lines')
            self.cond.notify_all()
        return self.job['id']

    def _end_job(self, error):
        j = self.job
        if not j or not j['running']:
            return
        j['running'], j['ended'], j['error'], j['paused'] = False, time.time(), error, False
        if error:
            self.say('err', f'"{j["name"]}" stopped: {error}')
        else:
            j['acked'] = len(j['lines'])
            self.say('sys', f'Finished "{j["name"]}" in {fmt_dur(j["ended"] - j["started"])}')

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
        threading.Thread(target=self.stop, args=(reason,), daemon=True).start()

    def stop(self, reason='Stopped by user', pen_up=None):
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
            self._end_job(reason)
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
            if line != '$$':
                self.say('tx', line)
            self.cond.notify_all()

    # ----- views -----
    def status(self, since=None):
        with self.lock:
            j = self.job
            job = None
            if j:
                frac = (j['cum'][j['acked'] - 1] / j['length']) if (j['length'] and j['acked']) else (j['acked'] / len(j['lines']))
                if not j['running'] and not j['error']:
                    frac = 1.0
                elapsed = (j['ended'] or time.time()) - j['started']
                eta = elapsed * (1 - frac) / frac if j['running'] and frac > 0.02 else None
                job = {'id': j['id'], 'name': j['name'], 'running': j['running'], 'paused': j['paused'],
                       'stopping': j['stopping'], 'error': j['error'], 'total': len(j['lines']), 'sent': j['acked'],
                       'queued': j['next'], 'progress': round(frac, 4), 'elapsed': round(elapsed, 1),
                       'eta': round(eta, 1) if eta is not None else None, 'started': j['started'], 'ended': j['ended']}
            wpos = [round(a - b, 3) for a, b in zip(self.mpos, self.wco)]
            st = {'bridge': VERSION, 'host': socket.gethostname(), 'connected': self.ser is not None,
                  'port': self.port, 'baud': self.baud, 'state': self.state, 'alarm': self.alarm,
                  'pos': wpos, 'job': job, 'error': self.error, 'seq': self.log_seq}
            if 130 in self.settings and 131 in self.settings:
                st['work'] = [self.settings[130], self.settings[131]]
            if since is not None:
                st['log'] = [e for e in self.log if e['seq'] > since]
            return st

    def job_detail(self):
        with self.lock:
            j = self.job
            if not j:
                return {'job': None}
            return {'job': {'id': j['id'], 'name': j['name'], 'total': len(j['lines']), 'moves': j['moves']}}


def fmt_dur(s):
    s = int(s)
    return f'{s // 3600} h {s % 3600 // 60} min' if s >= 3600 else f'{s // 60} min {s % 60} s'


# ---------------------------------------------------------------------------
#  HTTP API
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = f'PlotterBridge/{VERSION}'
    plotter: Plotter = None
    token = None

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
            return self._file('studio.html')
        if u.path == '/api/info':
            return self._send(200, {'name': 'plotter-bridge', 'version': VERSION, 'host': socket.gethostname(), 'auth': bool(self.token)})
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
            return self._send(200, self.plotter.job_detail())
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
            if cmd == 'connect':
                P.connect(body.get('port'), body.get('baud'))
            elif cmd == 'disconnect':
                P.disconnect()
            elif cmd == 'run':
                pen_up = body.get('penUp')
                jid = P.run(body.get('gcode', ''), body.get('name') or 'Plot', float(pen_up) if pen_up not in (None, '') else None)
                return self._send(200, {'ok': True, 'id': jid})
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
                P.queue(f'$J=G21G91X{dx:g}Y{dy:g}F{f:g}')
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
        # next to bridge.py (installed copy), else the repo root one folder up (running from a clone)
        path = next((p for p in (os.path.join(HERE, name), os.path.join(os.path.dirname(HERE), name)) if os.path.exists(p)), None)
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
    a = ap.parse_args()

    plotter = Plotter(a.port, a.baud, autoconnect=not a.no_autoconnect)
    Handler.plotter, Handler.token = plotter, a.token or None
    if not a.no_autoconnect:
        try:
            plotter.connect()
        except Exception as e:
            print(f'[sys] {e} — will keep looking', flush=True)
    srv = ThreadingHTTPServer((a.host, a.http_port), Handler)
    srv.daemon_threads = True
    host = socket.gethostname()
    print(f'[sys] Plotter Bridge {VERSION} — monitor: http://{host}.local:{a.http_port}/  studio: http://{host}.local:{a.http_port}/studio'
          + ('  (token required)' if a.token else ''), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
