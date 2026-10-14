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
from http.server import ThreadingHTTPServer
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

    def __init__(self, path=None, baud=None, report_ln=True, move_time=0.002):
        self.report_ln, self.move_time = report_ln, move_time
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
        idle = not self.cur and not self.planner
        if body == '$$':
            for k, v in ((130, 310), (131, 210), (22, 1)):
                self._emit(f'${k}={v}')
        elif body == '$I':
            self._emit('[VER:1.1h.20190825:]'); self._emit(f'[OPT:V,{self.BLOCKS},128]')
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
    P = B.Plotter('/dev/fake', 115200, autoconnect=False, store=B.JobStore(state_dir))
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


def main():
    helpers()
    for fn in (full_run, lambda t: crash_and_resume(t, True), lambda t: crash_and_resume(t, False), stop_and_resume, unplug, silent_reset, http_api):
        with tempfile.TemporaryDirectory() as tmp:
            fn(tmp)
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
