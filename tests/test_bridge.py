#!/usr/bin/env python3
"""Tests for the Plotter Bridge's checkpoint and resume, against a simulated GRBL (no hardware needed).

Run:  python3 tests/test_bridge.py
"""
import collections
import json
import math
import re
import sys
import tempfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'bridge'))
import bridge as B  # noqa: E402

failures = []


def check(cond, msg):
    print(('  ok   ' if cond else '  FAIL ') + msg)
    if not cond:
        failures.append(msg)


def wait_for(fn, timeout=20, step=0.02):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if fn():
            return True
        time.sleep(step)
    return False


class FakeGrbl:
    """GRBL 1.1 behind the bridge's SerialPort interface. A 15-block planner runs moves in (fast) real time;
    'ok' comes when a line is queued (moves) or done (G4, M3, G10); '?' reports MPos, WCO and Ln.
    `ink` records every pen-down move in physical coordinates, i.e. what really ends up on the paper."""
    BLOCKS = 15
    instances = []

    def __init__(self, path=None, baud=None, report_ln=True, move_time=0.002, legacy=False, nojog=False):
        self.report_ln, self.move_time = report_ln, move_time
        self.legacy, self.nojog = legacy, nojog   # legacy: GRBL 0.9 (no $J, no [VER:]); nojog: says 1.1 but has no jog command
        self.seen = []                            # every line received, as GRBL parsed it
        self.lock = threading.RLock()
        self.out = bytearray()
        self.rx = b''
        self.waiting = collections.deque()    # lines received, not yet taken in
        self.planner = collections.deque()    # [x, y, n, down] in machine coordinates
        self.cur, self.cur_t = None, 0.0
        self.mpos = [0.0, 0.0]
        self.offset = [0.0, 0.0]              # physical = machine + offset (a hardware reset zeroes the machine position)
        self.wco = [0.0, 0.0]                 # G54, kept in EEPROM
        self.s = 0.0
        self.hold = False
        self.dwell_until = 0.0
        self.ink = []
        self.done_n = 0                       # highest N whose line has fully run
        self.alive = True
        self.unplugged = False
        self.boot_until = 0.0                 # a rebooting board drops what arrives meanwhile
        FakeGrbl.instances.append(self)
        threading.Thread(target=self._run, daemon=True).start()
        threading.Timer(0.05, lambda: self._emit("Grbl 1.1h ['$' for help]")).start()

    # --- SerialPort interface ---
    def read(self, timeout=0.1):
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.unplugged:
                raise OSError('device disconnected')
            with self.lock:
                if self.out:
                    data, self.out = bytes(self.out), bytearray()
                    return data
            time.sleep(0.002)
        return b''

    def write(self, data):
        if self.unplugged:
            raise OSError('device disconnected')
        with self.lock:
            if time.time() < self.boot_until:
                return
            for c in data:
                ch = bytes([c])
                if ch == b'?':
                    self._emit(self._status())
                elif ch == b'!':
                    self.hold = True
                elif ch == b'~':
                    self.hold = False
                elif ch == b'\x18':
                    self._reset(hard=False)
                elif ch == b'\x85':
                    pass
                else:
                    self.rx += ch
                    while b'\n' in self.rx:
                        line, self.rx = self.rx.split(b'\n', 1)
                        self.waiting.append(line.decode().strip())

    def close(self):
        self.alive = False

    # --- test controls ---
    def crash(self, silent=False):
        """Power glitch: the controller reboots; the head stays where it physically is. `silent`: its banner gets lost."""
        with self.lock:
            self._reset(hard=True, banner=not silent)

    def unplug(self):
        self.unplugged = True

    # --- internals ---
    def _emit(self, text):
        with self.lock:
            self.out += (text + '\r\n').encode()

    def _phys(self, p):
        return [p[0] + self.offset[0], p[1] + self.offset[1]]

    def _reset(self, hard, banner=True):
        self.planner.clear(); self.waiting.clear(); self.rx = b''
        self.cur = None; self.hold = False; self.s = 0.0; self.dwell_until = 0.0
        if hard:
            self.offset = self._phys(self.mpos); self.mpos = [0.0, 0.0]
            self.boot_until = time.time() + 0.05
        if banner:
            self._emit("Grbl 1.1h ['$' for help]")

    def _status(self):
        state = 'Hold:0' if self.hold else 'Run' if (self.cur or self.planner or self.dwell_until > time.time()) else 'Idle'
        ln = f'|Ln:{self.cur[2]}' if self.report_ln and self.cur and self.cur[2] else ''
        return f'<{state}|MPos:{self.mpos[0]:.3f},{self.mpos[1]:.3f},0.000|FS:0,0{ln}|WCO:{self.wco[0]:.3f},{self.wco[1]:.3f},0.000>'

    def _pending_n(self):
        """Lowest line number that has not fully run (for checking the bridge never claims more than this)."""
        ns = [b[2] for b in ([self.cur] if self.cur else []) + list(self.planner) if b[2]]
        for line in self.waiting:
            m = re.match(r'N(\d+)', line)
            if m:
                ns.append(int(m.group(1)))
                break
        return min(ns) if ns else None

    def _run(self):
        while self.alive:
            with self.lock:
                now = time.time()
                if self.cur and not self.hold and now - self.cur_t >= self.move_time:
                    x, y, n, down = self.cur
                    if down:
                        a, b = self._phys(self.mpos), self._phys([x, y])
                        self.ink.append((round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))
                    self.mpos = [x, y]
                    if n:
                        self.done_n = max(self.done_n, n)
                    self.cur = None
                if not self.cur and self.planner and not self.hold:
                    self.cur, self.cur_t = self.planner.popleft(), now
                while self.waiting and self.dwell_until <= now and self._take(self.waiting[0], now):
                    self.waiting.popleft()
            time.sleep(0.0005)

    def _take(self, line, now):
        """Process one received line; False = not yet (planner full or waiting for moves to finish)."""
        m = re.match(r'N(\d+)\s*', line)
        n = int(m.group(1)) if m else 0
        body = line[m.end():] if m else line
        self.seen.append(body)
        idle = not self.cur and not self.planner
        if body == '$$':
            for k, v in ((130, 310), (131, 210), (22, 1)):
                self._emit(f'${k}={v}')
        elif body == '$I':
            if self.legacy:
                self._emit('[0.9j.20160326:]')
            else:
                self._emit('[VER:1.1h.20190825:]'); self._emit(f'[OPT:V,{self.BLOCKS},128]')
        elif body.startswith('$J='):
            if self.legacy or self.nojog:             # GRBL 0.9 reads this as the setting "$J"
                self._emit('error:2')
                return True
            w = {k: float(v) for k, v in re.findall(r'([A-Z])\s*([-+]?\d*\.?\d+)', body[3:])}
            last = self.planner[-1] if self.planner else self.cur or [*self.mpos, 0, False]
            if len(self.planner) + (1 if self.cur else 0) >= self.BLOCKS:
                return False
            self.planner.append([last[0] + w.get('X', 0), last[1] + w.get('Y', 0), 0, False])
        elif body == '$H':
            if not idle:
                return False
            self.mpos, self.offset = [0.0, 0.0], [0.0, 0.0]
        elif body.startswith('$'):
            pass
        else:
            w = {k: float(v) for k, v in re.findall(r'([A-Z])\s*([-+]?\d*\.?\d+)', body)}
            g = [int(v) for v in re.findall(r'G\s*(\d+)', body)]
            sync = 4 in g or 'M' in w or (10 in g)
            if sync and not idle:
                return False
            if 10 in g:                          # G10 L20 P1 X Y: the current position becomes work X Y
                self.wco = [self.mpos[0] - w.get('X', self.mpos[0] - self.wco[0]), self.mpos[1] - w.get('Y', self.mpos[1] - self.wco[1])]
            elif 4 in g:
                self.dwell_until = now + w.get('P', 0) * 0.01
            elif 'M' in w and 'S' in w:
                self.s = w['S']
            elif 'X' in w or 'Y' in w:
                if len(self.planner) + (1 if self.cur else 0) >= self.BLOCKS:
                    return False
                last = self.planner[-1] if self.planner else self.cur or [*self.mpos, 0, False]
                wx = w.get('X', last[0] - self.wco[0]); wy = w.get('Y', last[1] - self.wco[1])
                self.planner.append([wx + self.wco[0], wy + self.wco[1], n, self.s > 10])
                self._emit('ok')
                return True
            if n:
                self.done_n = max(self.done_n, n)
        self._emit('ok')
        return True


def make_job(strokes=60, seg=6, seed=1):
    """Studio-style G-code: per stroke a travel, pen down + dwell, `seg` moves, pen up + dwell."""
    import random
    R = random.Random(seed)
    L = ['G21', 'G90', 'M3 S0', 'G4 P0.3']
    expect = []
    for _ in range(strokes):
        x, y = R.uniform(20, 280), R.uniform(20, 190)
        L += [f'G1 X{x:.3f} Y{y:.3f} F4000', 'M3 S35', 'G4 P0.3']
        for k in range(seg):
            nx, ny = x + R.uniform(-8, 8), y + R.uniform(-8, 8)
            L.append(f'G1 X{nx:.3f} Y{ny:.3f}' + (' F2000' if k == 0 else ''))
            expect.append((round(x, 3), round(y, 3), round(nx, 3), round(ny, 3)))
            x, y = nx, ny
        L += ['M3 S0', 'G4 P0.3']
    L.append('G1 X0 Y0 F4000')
    return '\n'.join(L) + '\n', expect


def covered(expect, ink, tol=0.01):
    have = set((round(a, 2), round(b, 2), round(c, 2), round(d, 2)) for a, b, c, d in ink)
    miss = [s for s in expect if (round(s[0], 2), round(s[1], 2), round(s[2], 2), round(s[3], 2)) not in have]
    return miss


def new_bridge(state_dir, **fake):
    B.SerialPort = lambda path, baud: FakeGrbl(path, baud, **fake)
    P = B.Plotter('/dev/fake', 115200, autoconnect=False, store=B.JobStore(state_dir), machine=B.MachineStore(state_dir))
    return P


def helpers():
    print('G-code helpers')
    g, _ = make_job(3, 3)
    L = B.clean_lines(g)
    starts = B.stroke_starts(L, 0)
    check(starts == [i for i, l in enumerate(L) if l == 'M3 S35'], f'stroke starts are the pen-down lines {starts}')
    s1 = starts[1]
    check(B.resume_point(L, s1 + 4, 0) == s1, 'mid-stroke: resume from that stroke’s pen-down')
    check(B.resume_point(L, s1 - 1, 0) == s1 - 1, 'during travel: resume right there')
    pre = B.resume_preamble(L, s1, 0)
    x, y = re.search(r'X([\d.]+) Y([\d.]+)', L[s1 - 1]).groups()
    check(pre[:4] == ['G21', 'G90', 'M3 S0', 'G4 P0.3'] and pre[4] == f'G0 X{float(x):.3f} Y{float(y):.3f}',
          f'preamble: lift the pen, wait, travel to the stroke start ({pre})')
    check(B.clean_lines('N10 G1 X1 ; c\n(x)\n$H\n') == ['G1 X1', '$H'], 'old line numbers and comments are stripped')
    check(B.numbered(4, 'G1 X1') == 'N5 G1 X1' and B.numbered(4, '$H') == '$H', 'lines are numbered for Ln reports')
    check(list(B.line_kinds(['G1 X1', 'G4 P1', 'M3 S0', 'G10 L20 P1 X0'])) == [1, 2, 0, 0], 'line kinds: move, dwell, other')


def full_run(tmp):
    print('plot to the end')
    P = new_bridge(tmp)
    P.connect()
    g, expect = make_job(40)
    P.run(g, 'full', 0.0, {'color': '#123456'})
    check(wait_for(lambda: P.job['state'] == 'finished'), 'job finishes')
    fake = FakeGrbl.instances[-1]
    check(not covered(expect, fake.ink), 'every segment was drawn')
    disk = lambda: json.loads((Path(tmp) / 'job.json').read_text())
    check(wait_for(lambda: disk()['state'] == 'finished', 2) and disk()['done'] == disk()['total'], 'checkpoint says finished')
    st = P.status()
    check(st['job']['progress'] == 1 and st['job']['meta'] == {'color': '#123456'} and not st['job']['resumable'], 'status: 100%, meta kept, nothing to resume')
    P.disconnect()


def crash_and_resume(tmp, report_ln):
    label = 'with Ln' if report_ln else 'without Ln (fallback bounds)'
    print(f'controller reset mid-plot, bridge restart, resume — {label}')
    P = new_bridge(tmp, report_ln=report_ln)
    P.connect()
    g, expect = make_job(80)
    P.run(g, 'crashy', 0.0)
    total = len(P.job['lines'])
    fake = FakeGrbl.instances[-1]
    # watch the checkpoint against the truth while plotting
    worst, samples = 0, 0
    while P.job['done'] < total * 0.45:
        with P.lock, fake.lock:
            pend = fake._pending_n()
            truth = (pend - 1) if pend else fake.done_n
            worst = max(worst, P.job['done'] - truth)
            samples += 1
        time.sleep(0.003)
    check(worst <= 0, f'progress never runs ahead of what was drawn ({samples} samples, worst lead {worst} lines)')
    # crash in the middle of a stroke: the pen is down and has already drawn part of it
    wait_for(lambda: fake.cur and fake.cur[3] and fake.ink and fake.ink[-1][2:] == (round(fake.mpos[0], 3), round(fake.mpos[1], 3))
             and P.job['lines'][fake.cur[2] - 2].startswith('G1'), step=0.0005)
    with P.lock, fake.lock:
        pend = fake._pending_n()
        truth = (pend - 1) if pend else fake.done_n
        lag = truth - P.job['done']
        fake.crash()
    check(wait_for(lambda: P.job['state'] == 'interrupted'), 'reset during the plot → interrupted')
    j = P.status()['job']
    check(j['resumable'] and j['error'] == 'The controller reset during the plot', f'resumable: {j["error"]}')
    check(lag < 40, f'saved progress trails the pen by {lag} lines')
    starts = B.stroke_starts(P.job['lines'], 0)
    check(j['resume_at'] in starts or j['resume_at'] == j['done'], f'resume point {j["resume_at"]} is a stroke start (done {j["done"]})')
    disk = lambda: json.loads((Path(tmp) / 'job.json').read_text())
    check(wait_for(lambda: disk()['state'] == 'interrupted', 2) and disk()['done'] == j['done'], 'checkpoint on disk matches')
    meta = disk()

    # the bridge itself goes away while the job is marked running: simulate by rewriting the state
    meta['state'], meta['rev'] = 'running', meta['rev'] + 1
    (Path(tmp) / 'job.json').write_text(json.dumps(meta))
    P.disconnect()
    ink_before = list(fake.ink)

    P2 = new_bridge(tmp, report_ln=report_ln)
    j2 = P2.status()['job']
    check(j2 and j2['state'] == 'interrupted' and j2['resumable'] and j2['done'] == meta['done'], 'restarted bridge finds the unfinished plot')
    check('bridge stopped' in (j2['error'] or ''), f'and says why: {j2["error"]}')
    P2.connect()
    fake2 = FakeGrbl.instances[-1]
    fake2.mpos = [12.0, 34.0]                  # reconnecting resets the board: the controller no longer knows where it is
    P2.queue('$H')                             # re-home, as the recovery card asks
    time.sleep(0.2)
    P2.resume_job()
    check(wait_for(lambda: P2.job['state'] == 'finished', 30), 'resumed plot finishes')
    miss = covered(expect, ink_before + fake2.ink)
    check(not miss, f'every segment is on the paper after the resume ({len(miss)} missing)')
    redraw = len(set(ink_before) & set(fake2.ink))
    check(1 <= redraw <= 6, f'only the part of the interrupted stroke already drawn is traced again ({redraw} of 6 segments)')
    P2.disconnect()


def stop_and_resume(tmp):
    print('stop by hand, resume where it was')
    P = new_bridge(tmp)
    P.connect()
    g, expect = make_job(40)
    P.run(g, 'stopme', 0.0)
    total = len(P.job['lines'])
    wait_for(lambda: P.job['done'] > total * 0.3)
    P.stop()
    fake = FakeGrbl.instances[-1]
    check(P.job['state'] == 'stopped' and P.status()['job']['resumable'], 'stopped job can be resumed')
    check(fake.s == 0, 'pen lifted after stop')
    P.resume_job()
    check(wait_for(lambda: P.job['state'] == 'finished'), 'resumed plot finishes')
    check(not covered(expect, fake.ink), 'every segment drawn')
    P.discard_job()
    check(P.job is None and not (Path(tmp) / 'job.json').exists(), 'discard removes the checkpoint')
    P.disconnect()


def unplug(tmp):
    print('cable pulled mid-plot')
    P = new_bridge(tmp)
    P.connect()
    g, _ = make_job(40)
    P.run(g, 'unplug', 0.0)
    wait_for(lambda: P.job['done'] > 100)
    FakeGrbl.instances[-1].unplug()
    check(wait_for(lambda: P.job['state'] == 'interrupted'), 'unplugged → interrupted')
    check('Connection lost' in P.job['error'], P.job['error'])


def silent_reset(tmp):
    print('controller resets and its banner is lost')
    B.STALL_AFTER, stall = 0.8, B.STALL_AFTER
    try:
        P = new_bridge(tmp)
        P.connect()
        g, _ = make_job(40)
        P.run(g, 'silent', 0.0)
        wait_for(lambda: P.job['done'] > 100)
        FakeGrbl.instances[-1].crash(silent=True)
        check(wait_for(lambda: P.job['state'] == 'interrupted', 5), 'idle with lines unanswered → interrupted, not stuck')
        check('stopped answering' in (P.job['error'] or ''), P.job['error'])
        P.disconnect()
    finally:
        B.STALL_AFTER = stall


def http_api(tmp):
    print('HTTP API')
    P = new_bridge(tmp)
    P.connect()
    B.Handler.plotter, B.Handler.token = P, None
    srv = ThreadingHTTPServer(('127.0.0.1', 0), B.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}/api/'

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(req))

    g, _ = make_job(30)
    r = call('run', {'gcode': g, 'name': 'api', 'penUp': 0, 'meta': {'penId': 'p1'}})
    check(r.get('ok'), 'run')
    wait_for(lambda: P.job['done'] > 80)
    call('stop', {})
    st = call('status')
    check(st['job']['state'] == 'stopped' and st['job']['resumable'] and st['resume'], 'status reports a resumable job')
    d = call('job?gcode=1')['job']
    check(d['strokes'] and d['lines'] and d['resume_at'] is not None and d['meta'] == {'penId': 'p1'}, 'job detail: strokes, lines, resume point')
    pos = P.status()['pos']
    r = call('origin', {'x': pos[0] + 5, 'y': pos[1] + 6})
    check(r.get('ok'), 'origin')
    check(wait_for(lambda: abs(P.status()['pos'][0] - pos[0] - 5) < 1e-6 and abs(P.status()['pos'][1] - pos[1] - 6) < 1e-6, 2),
          'origin: the current position now reads as the given one (G10 L20)')
    call('origin', {'x': pos[0], 'y': pos[1]})
    wait_for(lambda: abs(P.status()['pos'][0] - pos[0]) < 1e-6, 2)
    r = call('job/resume', {'from': d['strokes'][2]})
    check(r.get('ok') and P.job['resume_from'] == d['strokes'][2], 'resume from a chosen stroke')
    check(wait_for(lambda: P.job['state'] == 'finished'), 'finishes')
    r = call('job/resume', {})
    check('finished' in r.get('error', ''), 'cannot resume a finished plot')
    call('job/discard', {})
    check(call('status')['job'] is None, 'discarded')
    srv.shutdown()
    P.disconnect()


def jogging(tmp):
    print('jogging on any GRBL')
    for label, fake in (('GRBL 1.1', {}), ('GRBL 0.9 (no $J)', {'legacy': True}), ('firmware that says 1.1 but rejects $J', {'nojog': True})):
        with tempfile.TemporaryDirectory() as d:
            P = new_bridge(d, **fake)
            P.connect()
            g = FakeGrbl.instances[-1]
            wait_for(lambda: P.settings.get(130), 3)
            at = lambda: tuple(round(v, 3) for v in P.status()['pos'][:2])
            P.jog(10, 5, 3000)
            check(wait_for(lambda: at() == (10.0, 5.0), 4), f'{label}: jog +10,+5 moves the pen ({at()})')
            P.jog(-30, 0, 3000)
            check(wait_for(lambda: at() == (0.0, 5.0), 4) or at() == (-20.0, 5.0) and 'GRBL 1.1' in label, f'{label}: a jog past the edge {"is clamped to the bed" if "1.1" not in label or fake else "goes on (GRBL 1.1 enforces its own soft limits)"} ({at()})')
            sent = [x for x in g.seen if x.startswith('$J=')]
            if fake.get('legacy'):
                check(not sent, f'{label}: never sends $J= ({sent})')
            elif fake.get('nojog'):
                check(len(sent) == 1, f'{label}: tried $J= once, then stopped trying ({len(sent)})')
            else:
                check(len(sent) == 2, f'{label}: uses $J= ({len(sent)})')
            P.disconnect()


def machine_profile(tmp):
    print('machine profile on the bridge')
    P = new_bridge(tmp)
    P.connect()
    B.Handler.plotter, B.Handler.token = P, None
    srv = ThreadingHTTPServer(('127.0.0.1', 0), B.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}/api/'

    def call(path, body=None):
        req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        return json.load(urllib.request.urlopen(req))

    info = call('info')
    m = call('machine')['machine']
    check(info['id'] == m['id'] and len(m['id']) >= 8 and m['profile'] is None and m['rev'] == 0, f"a fresh bridge has an id ({m['id']}) and no profile yet")
    wait_for(lambda: call('status').get('grbl', {}).get('settings', {}).get('130'), 3)
    st = call('status')
    check(st['grbl']['version'].startswith('1.1') and st['grbl']['settings']['130'] == 310 and st['grbl']['settings']['131'] == 210, f"status carries what GRBL reported: {st['grbl']}")
    prof = {'bedW': 310, 'bedH': 210, 'up': 0, 'down': 35, 'dwell': 0.3, 'feed': 2000, 'travel': 4000, 'park': True, 'mirrorX': True, 'header': 'G54', 'evil': 'x'}
    r = call('machine', {'name': 'Studio plotter', 'profile': prof, 'baseRev': 0})
    check(r['ok'] and r['machine']['rev'] == 1 and r['machine']['name'] == 'Studio plotter', 'saving the profile works')
    check('evil' not in r['machine']['profile'] and r['machine']['profile']['mirrorX'] is True and r['machine']['profile']['dwell'] == 0.3, 'only known settings are kept, types preserved')
    r = call('machine', {'profile': {'down': 'abc'}, 'baseRev': 1})
    check('error' in r and call('machine')['machine']['rev'] == 1, f"bad values are refused: {r.get('error')}")
    r = call('machine', {'profile': {'bedW': 99999}, 'baseRev': 1})
    check('error' in r, 'out-of-range values are refused')
    r = call('machine', {'profile': {**prof, 'down': 40}, 'baseRev': 0})
    check(r.get('conflict') and r['machine']['profile']['down'] == 35, 'a stale write is refused with the current settings')
    r = call('machine', {'profile': {**prof, 'down': 40}, 'baseRev': 1})
    check(r['ok'] and r['machine']['rev'] == 2, 'a write on the current revision goes through')
    check(call('status')['machine_rev'] == 2, 'status tells the revision, so other browsers notice changes')
    srv.shutdown()
    P.disconnect()
    P2 = new_bridge(tmp)
    m2 = P2.machine.get()
    check(m2['id'] == m['id'] and m2['name'] == 'Studio plotter' and m2['profile']['down'] == 40 and m2['rev'] == 2, 'after a restart: same id, name and profile')


def studio_and_https(tmp):
    print('studio is hosted, and the bridge can serve https')
    import http.client
    import os
    import shutil
    import ssl
    import subprocess
    P = new_bridge(tmp)
    P.connect()
    B.Handler.plotter, B.Handler.token, B.Handler.studio_url = P, None, 'https://studio.example/app/'
    real_find = B.find_file
    srv = ThreadingHTTPServer(('127.0.0.1', 0), B.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = '127.0.0.1', srv.server_address[1]

    def get(path, conn=None):
        c = conn or http.client.HTTPConnection(host, port, timeout=5)
        c.request('GET', path)
        r = c.getresponse()
        return r.status, r.getheader('Location'), r.read()

    B.find_file = lambda name: real_find(name) if name != 'studio.html' else None   # an installed bridge: no studio next to it
    st, loc, _ = get('/studio')
    check(st == 302 and loc == 'https://studio.example/app/', f'/studio sends you to the hosted studio ({st} {loc})')
    info = json.loads(get('/api/info')[2])
    check(info['studio'] == 'https://studio.example/app/' and info['studio_local'] is False, 'info tells where the studio is, and that none is kept here')
    st, _, body = get('/')
    check(st == 200 and b'Plotter Monitor' in body and b'studioLink' in body, 'the monitor is still served, with links to the hosted studio')
    B.find_file = lambda name: real_find(name)
    if real_find('studio.html'):
        st, _, body = get('/studio')
        check(st == 200 and b'Plot Studio' in body, 'running from a clone: /studio serves the repo copy')
    srv.shutdown()

    if not shutil.which('openssl'):
        print('  skip https (no openssl)')
        P.disconnect()
        return
    crt, key = os.path.join(tmp, 'c.pem'), os.path.join(tmp, 'k.pem')
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', crt, '-days', '1', '-subj', '/CN=localhost'],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    srv2 = ThreadingHTTPServer(('127.0.0.1', 0), B.Handler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)
    srv2.socket = ctx.wrap_socket(srv2.socket, server_side=True)   # what --cert/--key do in main()
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    cctx = ssl.create_default_context()
    cctx.check_hostname, cctx.verify_mode = False, ssl.CERT_NONE
    c = http.client.HTTPSConnection(host, srv2.server_address[1], timeout=5, context=cctx)
    st, _, body = get('/api/info', c)
    check(st == 200 and json.loads(body)['name'] == 'plotter-bridge', 'with a certificate the API answers over https')
    srv2.shutdown()
    P.disconnect()
    # …and the real command line: bridge.py --cert --key
    import socket
    s = socket.socket(); s.bind(('127.0.0.1', 0)); free = s.getsockname()[1]; s.close()
    proc = subprocess.Popen([sys.executable, str(Path(B.__file__)), '--no-autoconnect', '--http-port', str(free), '--host', '127.0.0.1', '--cert', crt, '--key', key,
                             '--state', os.path.join(tmp, 'cli'), '--studio-url', 'https://studio.example/'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ok = False
        for _ in range(60):
            try:
                c = http.client.HTTPSConnection('127.0.0.1', free, timeout=2, context=cctx)
                st, _, body = get('/api/info', c)
                ok = st == 200 and json.loads(body)['studio'] == 'https://studio.example/'
                break
            except OSError:
                time.sleep(0.1)
        check(ok, 'bridge.py --cert --key --studio-url serves https and reports the studio address')
    finally:
        proc.terminate()
        proc.wait(5)


def self_update(tmp):
    print("bridge updates itself from a release")
    import hashlib, io, os, tarfile
    src = open(B.__file__, 'rb').read().decode()
    def tarball(version, extra=None):
        body = re.sub(r"^VERSION = .*$", f"VERSION = '{version}'", src, flags=re.M).encode()
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as t:
            for name, data in {'plotter-bridge/bridge.py': body, 'plotter-bridge/monitor.html': b'<p>new monitor', 'plotter-bridge/evil.sh': b'rm -rf /', '../escape.py': b'x', **(extra or {})}.items():
                ti = tarfile.TarInfo(name); ti.size = len(data); t.addfile(ti, io.BytesIO(data))
        return buf.getvalue()
    rel = {}
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            if self.path.endswith('/releases/latest'):
                blob = rel['blob']; port = self.server.server_address[1]
                data = json.dumps({'tag_name': rel['tag'], 'assets': [{'name': 'plotter-bridge.tar.gz', 'browser_download_url': f'http://127.0.0.1:{port}/dl',
                                    'digest': rel.get('digest', 'sha256:' + hashlib.sha256(blob).hexdigest())}]}).encode()
            else:
                data = rel['blob']
            self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    api = f'http://127.0.0.1:{srv.server_address[1]}'
    P = new_bridge(tmp + '/state')
    folder = tmp + '/install'; os.makedirs(folder)
    open(folder + '/bridge.py', 'w').write('old'); open(folder + '/monitor.html', 'w').write('old monitor')
    restarts = []
    def fresh(): return B.Updater(P, 'x/y', api, 3600, folder, lambda: restarts.append(1))
    B.UPDATE_RETRY = 0.05

    rel.update(tag='v%d.%d.%d' % (tuple(int(x) for x in B.VERSION.split('.'))), blob=tarball(B.VERSION))
    check(fresh().check() is None and not restarts, 'the same version is left alone')
    rel.update(tag='v0.0.1', blob=tarball('0.0.1'))
    check(fresh().check() is None and not restarts, 'an older release is ignored')
    rel.update(tag='v9.9.9-rc1', blob=tarball('9.9.9'))
    check(fresh().check() is None and not restarts, 'a pre-release tag is ignored')

    rel.update(tag='v9.9.9', blob=tarball('9.9.9'), digest='sha256:' + '0' * 64)
    u = fresh(); check(u.check() is None and u.info()['state'] == 'error' and open(folder + '/bridge.py').read() == 'old', 'a download that does not match its checksum is rejected')
    rel.pop('digest')
    rel['blob'] = tarball('9.9.8')
    u = fresh(); check(u.check() is None and open(folder + '/bridge.py').read() == 'old', 'a bridge.py that reports another version is rejected')
    rel['blob'] = tarball('9.9.9', {'plotter-bridge/bridge.py': b'def (:'})
    u = fresh(); check(u.check() is None and open(folder + '/bridge.py').read() == 'old', 'a bridge.py that does not even compile is rejected')

    rel['blob'] = tarball('9.9.9')
    P.job = {'running': True}
    u = fresh(); th = threading.Thread(target=u.check, daemon=True); th.start()
    time.sleep(0.6)
    check(u.info()['state'] == 'waiting' and open(folder + '/bridge.py').read() == 'old' and not restarts, 'while a plot is running the update waits')
    P.job = None; th.join(10)
    check(restarts == [1] and 'VERSION = \'9.9.9\'' in open(folder + '/bridge.py').read(), 'when idle it is installed and the bridge restarts')
    check(open(folder + '/bridge.py.prev').read() == 'old' and open(folder + '/monitor.html').read() == '<p>new monitor', 'the old file is kept as .prev; the monitor is updated too')
    check(sorted(os.listdir(folder)) == ['bridge.py', 'bridge.py.prev', 'monitor.html', 'monitor.html.prev'] and not os.path.exists(tmp + '/escape.py'), 'nothing else is written')
    srv.shutdown()


def main():
    helpers()
    for fn in (full_run, lambda t: crash_and_resume(t, True), lambda t: crash_and_resume(t, False), stop_and_resume, unplug, silent_reset, http_api, machine_profile, studio_and_https, jogging, self_update):
        with tempfile.TemporaryDirectory() as tmp:
            fn(tmp)
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
