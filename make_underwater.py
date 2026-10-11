#!/usr/bin/env python3
"""Generate underwater.svg: a Maldives reef scene as pen-plotter line art (A4 landscape, mm).

Every shape is built as polylines. Closed shapes hide whatever lies behind them
(hidden-line removal), so the SVG contains only visible strokes and plots as-is.
Objects are added back-to-front.
"""
import math, random, re
import numpy as np

W, H = 297.0, 210.0
random.seed(7)
objects = []   # back-to-front: (lines, occluding polygons)


# ---------------------------------------------------------------- geometry helpers
def closed(p):
    p = np.asarray(p, float)
    return p if np.allclose(p[0], p[-1]) else np.vstack([p, p[:1]])

def add(lines, occl=()):
    objects.append(([np.asarray(l, float) for l in lines if len(l) > 1], [closed(o) for o in occl]))

def bez(P, t):
    P = P.copy()
    while len(P) > 1: P = (1 - t) * P[:-1] + t * P[1:]
    return P[0]

def parse(d, n=14):
    """Absolute M/L/C/Q/Z path string -> list of (points, is_closed)."""
    toks = re.findall(r"[MLCQZ]|-?\d*\.?\d+", d)
    out, cur, cmd, i = [], [], None, 0
    while i < len(toks):
        if toks[i] in "MLCQZ":
            cmd = toks[i]; i += 1
            if cmd == "Z":
                cur.append(cur[0]); out.append((cur, True)); cur = []
            continue
        k = {"M": 2, "L": 2, "C": 6, "Q": 4}[cmd]
        vals = [float(v) for v in toks[i:i + k]]; i += k
        if cmd == "M":
            if len(cur) > 1: out.append((cur, False))
            cur = [tuple(vals)]; cmd = "L"
        elif cmd == "L":
            cur.append(tuple(vals))
        else:
            P = np.vstack([cur[-1], np.reshape(vals, (-1, 2))])
            cur += [tuple(bez(P, t)) for t in np.linspace(0, 1, n + 1)[1:]]
    if len(cur) > 1: out.append((cur, False))
    return out

def T(x, y, s=1.0, rot=0.0, flip=False, sy=1.0):
    """Local -> page transform: scale, optional mirror, rotate (deg), place, squash page-y."""
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    def f(pts):
        p = np.array(pts, float).reshape(-1, 2) * s
        if flip: p[:, 0] *= -1
        return np.column_stack([x + p[:, 0] * c - p[:, 1] * sn, y + (p[:, 0] * sn + p[:, 1] * c) * sy])
    return f

def part(tf, d="", details="", solid=(), lines=()):
    """One opaque piece: outline path `d` + `solid` polys hide what is behind; details are just drawn."""
    L, O = [], []
    for pts, cl in parse(d):
        p = tf(pts); L.append(p)
        if cl: O.append(p)
    for poly in solid:
        p = tf(poly); L.append(p); O.append(p)
    L += [tf(pts) for pts, _ in parse(details)] + [tf(l) for l in lines]
    add(L, O)

def ellipse(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, n=48):
    t = np.linspace(a0, a1, n)
    return np.column_stack([cx + rx * np.cos(t), cy + ry * np.sin(t)])

def circle(cx, cy, r):
    return ellipse(cx, cy, r, r, n=max(12, int(r * 10)))

def wiggle(x, y, ang, length, curl=0.0, wav=0.0, ph=0.0, n=24):
    """Centre line starting at (x, y) heading `ang` (rad, y down), bending by `curl`, waving by `wav`."""
    pts = [(x, y)]
    for k in range(n):
        f = k / n
        a = ang + curl * f + wav * math.sin(ph + 2 * math.pi * f)
        x += length / n * math.cos(a); y += length / n * math.sin(a)
        pts.append((x, y))
    return np.array(pts)

def tube(c, w0, w1, ncap=8):
    """Closed outline of a tapered tube around centre line c, with a rounded tip."""
    c = np.asarray(c, float)
    t = np.gradient(c, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
    nrm = np.column_stack([-t[:, 1], t[:, 0]])
    w = np.linspace(w0, w1, len(c))[:, None] / 2
    left, right = c + nrm * w, c - nrm * w
    a, r = math.atan2(nrm[-1, 1], nrm[-1, 0]), w[-1, 0]
    cap = [c[-1] + r * np.array([math.cos(a - k * math.pi / ncap), math.sin(a - k * math.pi / ncap)])
           for k in range(1, ncap)]
    return np.vstack([left, cap, right[::-1], left[:1]])

def resample(p, step=0.25):
    seg = np.diff(p, axis=0)
    n = np.maximum(1, np.ceil(np.hypot(*seg.T) / step)).astype(int)
    return np.vstack([p[:1]] + [a + d * (np.arange(1, k + 1) / k)[:, None] for a, d, k in zip(p[:-1], seg, n)])

def runs(p, mask):
    out, start = [], None
    for i, m in enumerate(np.append(mask, False)):
        if m and start is None: start = i
        elif not m and start is not None:
            if i - start > 1: out.append(p[start:i])
            start = None
    return out

def dashes(p, on, off, phase=0.0):
    p = resample(np.asarray(p, float), 0.5)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))] + phase
    return runs(p, d % (on + off) < on)

def surface(x): return 22 + 0.8 * np.sin(np.asarray(x) / 6) + 0.6 * np.sin(np.asarray(x) / 2.3 + 1)
def sand(x):    return 178 + 3 * np.sin(np.asarray(x) / 17) + 2 * np.sin(np.asarray(x) / 7 + 1)


# ---------------------------------------------------------------- sky and surface
def sky():
    add([circle(270, 10, 5.5)])
    for k in range(12):
        a = k * math.pi / 6
        add([[(270 + 7.5 * math.cos(a), 10 + 7.5 * math.sin(a)), (270 + 10 * math.cos(a), 10 + 10 * math.sin(a))]])
    for bx, by in ((205, 9), (214, 6), (222, 11)):
        add(parse(f"M {bx-3} {by} C {bx-2} {by-1.5} {bx-1} {by-1.5} {bx} {by} "
                  f"C {bx+1} {by-1.5} {bx+2} {by-1.5} {bx+3} {by}")[0][:1])

def light_rays():
    for x0 in np.arange(200, 300, 13):
        y0 = float(surface(x0)) + 3
        L = random.uniform(35, 65)
        for d in dashes([(x0, y0), (x0 - 0.3 * L, y0 + L)], 7, 5, random.uniform(0, 12)):
            add([d])

def current():
    """Streamlines of the current flowing left -> right, with chevrons."""
    for y0, ph in ((48, 0.0), (70, 1.3), (92, 2.1), (114, 0.6), (136, 2.8), (156, 1.9)):
        xs = np.linspace(-5, W + 5, 300)
        ys = y0 + 4 * np.sin(2 * math.pi * xs / 95 + ph) + 1.5 * np.sin(xs / 13 + ph)
        p = np.column_stack([xs, ys])
        for d in dashes(p, 9, 4, random.uniform(0, 13)):
            add([d])
        arc = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
        for s in np.arange(random.uniform(10, 40), arc[-1], 48):
            i = int(np.searchsorted(arc, s))
            t = p[i + 1] - p[i - 1]; t /= np.linalg.norm(t); n = np.array([-t[1], t[0]])
            add([[p[i] - 3 * t + 1.8 * n, p[i], p[i] - 3 * t - 1.8 * n]])

def sea_surface():
    xs = np.linspace(0, W, 600)
    add([np.column_stack([xs, surface(xs)])])
    for d in dashes(np.column_stack([xs, surface(xs + 3) + 2.5]), 5, 6):
        add([d])

def island():
    xs = np.linspace(6, 54, 60)
    top = surface(xs) - 6 * np.sin(np.pi * (xs - 6) / 48) ** 0.7
    hump = np.column_stack([xs, top])
    add([hump], [np.vstack([hump, [(54, 25), (6, 25)]])])
    trunk = wiggle(30, float(top[30]) + 0.5, -math.pi / 2 + 0.25, 13, curl=-0.4, n=16)
    add([tube(trunk, 1.6, 1.0)], [tube(trunk, 1.6, 1.0)])
    tx, ty = trunk[-1]
    for a, cu in ((-170, -0.9), (-140, -1.0), (-110, -0.8), (-70, 0.8), (-35, 1.0), (-5, 0.9)):
        leaf = tube(wiggle(tx, ty, math.radians(a), 7.5, curl=cu, n=14), 1.5, 0.2)
        add([leaf], [leaf])
    add([circle(tx - 0.8, ty + 1.2, 0.8)], [circle(tx - 0.8, ty + 1.2, 0.8)])

def dhoni(x, y, s):
    """Traditional Maldivian boat, sitting on the surface."""
    tf = T(x, y, s)
    part(tf, "M 5 -36 L 22 -12 L 5 -9 Z", "M 6 -30 L 15 -15")                       # sail
    part(tf, "M -22 -5 L -22 -11 L -6 -11 L -6 -5 Z", "M -24 -11 L -4 -11 M -14 -11 L -14 -5")
    part(tf, "M 3.3 -5 L 3.3 -38 L 4.7 -38 L 4.7 -5 Z")                              # mast
    part(tf, "M -30 -5 L 22 -5 C 27 -6 31 -10 32 -16 L 34 -16 C 33 -8 29 -1 22 3 "
             "C 5 6 -18 5 -28 2 Z",
         "M -28 -1.5 C -10 0.5 10 0.5 25 -1.5 M 31 -14 C 30 -10 28 -7 24 -4")


# ---------------------------------------------------------------- creatures
def shark(x, y, s, rot=0, flip=False):
    tf = T(x, y, s, rot, flip)
    part(tf, "M 50 1 C 48 -4 38 -9 20 -10 L 12 -10 C 8 -16 4 -24 0 -26 C -1 -18 -3 -12 -6 -9 "
             "C -18 -8 -32 -5 -40 -3 L -44 -2 C -48 -8 -54 -18 -58 -24 C -56 -14 -54 -6 -52 0 "
             "C -54 4 -55 8 -56 12 C -51 8 -47 4 -44 2 L -40 3 C -34 5 -26 6 -20 7 "
             "C -20 11 -22 13 -24 14 C -18 13 -14 11 -12 8 C 0 9 8 10 14 9 "
             "C 10 16 4 22 -2 26 C 4 20 12 14 22 9 C 32 8 44 7 50 1 Z",
         "M 26 -5 C 27 -2 27 1 26 4 M 23.5 -5 C 24.5 -2 24.5 1 23.5 4.5 M 21 -5 C 22 -2 22 1 21 5 "
         "M 45 4 C 42 5.5 39 5.5 37 5 M 46 2.5 C 30 3.5 0 2.5 -38 0.5 "
         "M -30 -5.5 L -33 -9 L -35 -4.8",
         lines=[circle(38, -3, 1.2)])

def manta(x, y, s, rot=0):
    tf = T(x, y, s, rot)
    part(tf, "M -8 -28 C -10 -22 -10 -18 -9 -16 C -22 -16 -42 -10 -50 4 C -38 2 -22 8 -12 14 "
             "C -8 18 -4 22 -2 24 L 2 24 C 4 22 8 18 12 14 C 22 8 38 2 50 4 "
             "C 42 -10 22 -16 9 -16 C 10 -18 10 -22 8 -28 C 6 -24 5 -21 3 -20 L -3 -20 "
             "C -5 -21 -6 -24 -8 -28 Z",
         "M -6 -14 C -8 0 -6 12 -2 22 M 6 -14 C 8 0 6 12 2 22 "
         "M -12 -12 C -25 -11 -38 -6 -44 0 M 12 -12 C 25 -11 38 -6 44 0 "
         "M -14 -6 C -22 -4 -28 -1 -32 2 M 14 -6 C 22 -4 28 -1 32 2 "
         "M -3 -20 C -1 -19 1 -19 3 -20 M 0 24 C 1 32 -1 40 1 52",
         lines=[circle(-8.5, -17.5, 0.9), circle(8.5, -17.5, 0.9)])

def stingray(x, y, s, rot=0, sy=1.0):
    tf = T(x, y, s, rot, sy=sy)
    part(tf, "M 0 18 C 2 35 -3 50 2 72 L 2.6 72 C -2 50 3 35 1.2 18 Z", "M 1 36 L 4 40")
    part(tf, "M 0 -22 C 12 -22 26 -10 26 0 C 26 8 12 16 0 18 C -12 16 -26 8 -26 0 "
             "C -26 -10 -12 -22 0 -22 Z",
         "M -5 15 C -7 19 -5 22 -2 20 M 5 15 C 7 19 5 22 2 20 M 0 -12 C -1 -2 -1 8 0 16",
         lines=[circle(-4, -10, 1.2), circle(4, -10, 1.2)]
               + [circle(px, py, 0.8) for px, py in ((-14, -2), (13, -4), (-9, 7), (10, 6), (-18, 3), (17, 2))])

def barracuda(x, y, s, rot=0, flip=True):
    tf = T(x, y, s, rot, flip)
    part(tf, "M 2 -4.8 L -2 -10 L -6 -4.6 Z")
    part(tf, "M -24 -4 L -27 -8 L -30 -3.6 Z")
    part(tf, "M -22 4 L -26 7.5 L -29 3.4 Z")
    part(tf, "M 50 0 C 44 -3 30 -5 10 -5 C -10 -5 -30 -4 -40 -2 C -43 -5 -46 -8 -50 -10 "
             "C -48 -4 -47 -1 -48 0 C -47 1 -48 4 -50 10 C -46 8 -43 5 -40 2 "
             "C -30 4 -10 5 10 5 C 30 5 44 3 50 0 Z",
         "M 50 0 L 38 1.3 M 34 0 C 10 0.6 -20 0.3 -38 0 M 30 1 L 24 3.5 L 27 1 "
         "M 22 -4.6 L 20 -2 M 12 -4.9 L 10 -2.2 M -8 -4.8 L -10 -2.2 M -18 -4.5 L -20 -2 M -32 -3.4 L -34 -1.4",
         lines=[circle(41, -1.3, 1.1)])

def turtle(x, y, s, rot=0):
    tf = T(x, y, s, rot)
    part(tf, "M -12 15 C -20 19 -24 26 -21 30 C -17 28 -13 24 -7 21 Z")
    part(tf, "M 12 15 C 20 19 24 26 21 30 C 17 28 13 24 7 21 Z")
    part(tf, "M -2 22 L 0 28 L 2 22 Z")
    part(tf, "M -15 -12 C -28 -20 -42 -20 -50 -12 C -40 -9 -28 -6 -17 -3 Z",
         "M -24 -15.5 L -26 -9 M -33 -16.5 L -34 -10 M -41 -15 L -41 -11")
    part(tf, "M 15 -12 C 28 -20 42 -20 50 -12 C 40 -9 28 -6 17 -3 Z",
         "M 24 -15.5 L 26 -9 M 33 -16.5 L 34 -10 M 41 -15 L 41 -11")
    part(tf, "M -5 -21 C -7 -28 -5 -34 0 -35 C 5 -34 7 -28 5 -21 Z",
         "M -3 -25 L 3 -25 M -2 -32 L 2 -32", lines=[circle(-3, -29.5, 0.9), circle(3, -29.5, 0.9)])
    ex = lambda yy: 13 * math.sqrt(max(0.0, 1 - (yy / 18.5) ** 2))       # inner ellipse half-width
    det = [ellipse(0, 0, 13, 18.5)]
    det += [np.array([(-6, yy), (6, yy)]) for yy in (-10, -1, 8)]
    det += [np.array([(sx * 6, -16), (sx * 6, 16)]) for sx in (-1, 1)]
    det += [np.array([(sx * 6, yy), (sx * ex(yy + 2), yy + 2)]) for sx in (-1, 1) for yy in (-10, -1, 8)]
    det += [np.array([(13 * math.cos(a), 18.5 * math.sin(a)), (18 * math.cos(a), 24 * math.sin(a))])
            for a in np.linspace(0, 2 * math.pi, 19)[:-1] + 0.17]
    part(tf, solid=[ellipse(0, 0, 18, 24, n=64)], lines=det)

def clownfish(x, y, s, rot=0, flip=False):
    tf = T(x, y, s, rot, flip)
    part(tf, "M 4 -5.6 C 2 -9.5 -4 -9.5 -7 -4.4 Z")
    part(tf, "M 0 5.5 C -2 8.5 -5 8.5 -6 4.5 Z")
    stripes = "".join(f"M {sx-o} -6.2 C {sx-o+1} -2 {sx-o+1} 2 {sx-o} 6.2 " for sx in (5, -1) for o in (-0.8, 0.8))
    part(tf, "M 10 0 C 9 -4 5 -6 0 -6 C -4 -6 -7 -4 -9 -2 L -13 -5 C -14 -2 -14 2 -13 5 "
             "L -9 2 C -7 4 -4 6 0 6 C 5 6 9 4 10 0 Z",
         stripes + "M -7.5 -3 C -7 -1 -7 1 -7.5 3 M 2 1 C 0 2 -1 3 0 4",
         lines=[circle(7, -1.5, 0.8)])

def reef_fish(x, y, s, rot=0, flip=True):
    tf = T(x, y, s, rot, flip)
    part(tf, "M 6 0 C 4 -3.5 -1 -3.5 -4 0 L -7 -3 L -7 3 L -4 0 C -1 3.5 4 3.5 6 0 Z",
         "M 1.5 -2.5 C 2.3 -1 2.3 1 1.5 2.5", lines=[circle(3.8, -0.6, 0.45)])

def bubbles(x, y, ytop):
    k = 0
    while y > ytop:
        r = min(0.5 + 0.07 * k, 2.0)
        bx = x + 2.5 * math.sin(k * 0.9) + 0.25 * k
        add([circle(bx, y, r)], [circle(bx, y, r)])
        if k % 4 == 2:
            add([circle(bx + 2.2 * r, y + r, 0.6 * r)], [circle(bx + 2.2 * r, y + r, 0.6 * r)])
        y -= 2.4 * r + 1.6 + random.uniform(0, 1.5)
        k += 1

def diver(x, y, s, rot=0):
    tf = T(x, y, s, rot)
    part(tf, "M -18 6.2 L -30 12.5 C -30.5 15 -29.5 17 -28 18 L -20 9.8 Z",
         "M -20 8 L -29 15.5")                                                     # far fin
    part(tf, solid=[tube([(-1, 1), (-10, 4), (-19.5, 8.5)], 4, 3)])                 # far leg
    part(tf, solid=[tube([(16, 0), (21, 4), (26.5, 8.5)], 3, 2.4)])                 # far arm
    part(tf, "M 3 -10 L 17 -10 C 19 -10 20 -9 20 -7.25 C 20 -5.5 19 -4.5 17 -4.5 L 3 -4.5 "
             "C 1 -4.5 0 -5.5 0 -7.25 C 0 -9 1 -10 3 -10 Z", "M 6 -10 L 6 -4.5")    # tank
    part(tf, "M 20 -8 L 22.5 -8 L 22.5 -6.3 L 20 -6.3 Z")                           # valve
    part(tf, "M 21 -4.5 C 15 -5.5 5 -5.5 -1 -4 C -3 -2 -3 2 -1 3 C 5 4.5 15 4.5 21 3 "
             "C 23 1.5 23 -3 21 -4.5 Z", "M 12 -5.2 L 12 4.2 M 4 -5.3 L 4 4")      # torso
    part(tf, "M -20 -3 L -35 -7.5 C -36.5 -4 -36.5 -0.5 -35 1.5 L -20 1.2 Z",
         "M -22 -2 L -34 -5.5 M -22 0.3 L -34 0.5")                                 # near fin
    part(tf, solid=[tube([(-1, 0.5), (-10, 0), (-21, -0.8)], 4.4, 3.4)])            # near leg
    part(tf, solid=[circle(25.5, -1.5, 4)], details="M 21.8 -3.6 L 27 -3.2")        # head
    part(tf, "M 27 -4.2 L 30.6 -4.2 C 31.1 -2.6 31.1 -0.6 30.6 0.6 L 27 0.6 Z")      # mask
    part(tf, solid=[tube([(18, 1), (23, 5), (29.5, 7.5)], 3.2, 2.6), circle(29.5, 2.4, 1.1)])
    part(tf, details="M 28.6 3.2 C 26 7 23 0 21.5 -6.5")                            # hose
    mx, my = tf([(31, 1.5)])[0]
    bubbles(mx, my - 2, float(surface(mx)) + 3)


# ---------------------------------------------------------------- seabed and reef
def seabed():
    xs = np.linspace(-2, W + 2, 300)
    top = np.column_stack([xs, sand(xs)])
    add([top], [np.vstack([top, [(W + 2, H + 2), (-2, H + 2)]])])
    for _ in range(75):
        x0 = random.uniform(0, W); y0 = random.uniform(float(sand(x0)) + 4, H - 2)
        L = random.uniform(5, 13); xx = np.linspace(x0, x0 + L, 14)
        add([np.column_stack([xx, y0 + 0.6 * np.sin((xx - x0) / L * 2 * math.pi)])])

def rock(x, r):
    y = float(sand(x)) + 1.5
    th = np.linspace(math.pi, 2 * math.pi, 40)
    rr = r * (1 + 0.12 * np.sin(3 * th + x) + 0.06 * np.sin(7 * th))
    poly = np.vstack([np.column_stack([x + rr * np.cos(th), y + 0.7 * rr * np.sin(th)]), [(x - r, y)]])
    add([poly[:-1]], [poly])
    for _ in range(3):
        cx, cy = x + random.uniform(-0.5, 0.5) * r, y - random.uniform(0.15, 0.45) * r
        add([circle(cx, cy, random.uniform(0.4, 0.9))])

def staghorn(x, size, depth=4):
    y = float(sand(x)) + 1
    def br(x, y, a, L, w, d):
        pts = wiggle(x, y, a, L, curl=random.uniform(-0.3, 0.3), n=12)
        poly = tube(pts, w, w * 0.75); add([poly], [poly])
        if d == 0: return
        ex, ey = pts[-1]
        for side in (-1, 1):
            na = min(max(a + side * random.uniform(0.3, 0.7), -math.pi + 0.25), -0.25)
            br(ex, ey, na, L * random.uniform(0.6, 0.8), w * 0.75, d - 1)
        if random.random() < 0.5 and d > 1:
            mx, my = pts[len(pts) // 2]
            br(mx, my, a + random.choice((-1, 1)) * 0.8, L * 0.5, w * 0.7, d - 2)
    br(x, y, -math.pi / 2, size, size * 0.24, depth)

def sea_fan(x, size):
    y = float(sand(x)) + 1
    trunk = wiggle(x, y, -math.pi / 2, size * 0.18, n=8)
    lines = []
    def br(x, y, a, L, d):
        pts = wiggle(x, y, a, L, curl=random.uniform(-0.25, 0.25), n=10)
        lines.append(pts)
        if d == 0: return
        for side in (-1, 1):
            br(*pts[-1], a + side * random.uniform(0.18, 0.42), L * 0.8, d - 1)
    br(*trunk[-1], -math.pi / 2, size * 0.2, 6)
    add(lines)
    add([tube(trunk, 2.6, 1.6)], [tube(trunk, 2.6, 1.6)])

def brain_coral(x, rx, ry):
    y = float(sand(x)) + 1.5
    th = np.linspace(math.pi, 2 * math.pi, 80)
    dome = np.column_stack([x + rx * np.cos(th), y + ry * np.sin(th)])
    lines = [dome]
    for k in range(1, 6):
        r = k / 6 + 0.035 * np.sin(22 * th + k * 1.7)
        lines.append(np.column_stack([x + rx * r * np.cos(th), y + ry * r * np.sin(th)]))
    add(lines, [dome])

def table_coral(x, rx, h):
    y = float(sand(x)) + 1
    add([[(x - 4, y), (x - 2, y - h), (x + 2, y - h), (x + 4, y)]],
        [[(x - 4, y), (x - 2, y - h), (x + 2, y - h), (x + 4, y)]])
    cy, ry = y - h - 2, rx * 0.2
    upper = ellipse(x, cy, rx, ry, math.pi, 2 * math.pi, 40)
    lower = ellipse(x, cy + 3, rx, ry, 0, math.pi, 40)
    outline = np.vstack([upper, lower])
    rim = ellipse(x, cy, rx, ry, 0, math.pi, 40)
    spokes = [np.array([(x, cy), (x + 0.92 * rx * math.cos(a), cy + 0.92 * ry * math.sin(a))])
              for a in np.linspace(0, 2 * math.pi, 15)[:-1]]
    drips = [np.array([(px, py), (px, py + random.uniform(1, 2.5))]) for px, py in lower[3:-3:3]]
    add([outline, rim] + spokes + drips, [outline])

def sponges(x):
    y = float(sand(x)) + 1
    for dx, hgt, r in ((-6, 16, 3.2), (6, 20, 3.0), (0, 26, 3.6)):
        cx = x + dx; top = y - hgt
        th = np.linspace(0, 1, 20)
        left = np.column_stack([cx - r - 0.6 * np.sin(th * 6), y - th * hgt])
        right = np.column_stack([cx + r + 0.6 * np.sin(th * 6 + 1), y - th * hgt])
        cap = ellipse(cx, top, r + 0.6 * math.sin(6 + 1) * 0.5, r * 0.35, math.pi, 2 * math.pi, 20)
        poly = np.vstack([left, cap, right[::-1]])
        add([poly, ellipse(cx, top, r, r * 0.35), ellipse(cx, top + 0.3, r * 0.6, r * 0.2)], [poly])

def seagrass(x, n=4):
    for _ in range(n):
        bx = x + random.uniform(-3, 3)
        c = wiggle(bx, float(sand(bx)) + 1.5, -math.pi / 2 + random.uniform(-0.3, 0.3),
                   random.uniform(9, 20), wav=0.25, ph=random.uniform(0, 6), n=20)
        poly = tube(c, 1.4, 0.5); add([poly], [poly])

def anemone(x, w):
    y = float(sand(x)) + 1
    top = y - w * 0.35
    th = np.linspace(0, 1, 20)
    left = np.column_stack([x - w * (0.3 + 0.2 * th) - 0.6 * np.sin(th * 5), y - th * (y - top)])
    right = np.column_stack([x + w * (0.3 + 0.2 * th) + 0.6 * np.sin(th * 5), y - th * (y - top)])
    col = np.vstack([left, right[::-1]])
    add([col, [(x - w * 0.15, y), (x - w * 0.18, top)], [(x + w * 0.12, y), (x + w * 0.16, top)]], [col])
    tents = []
    for i in range(26):
        t = i / 25
        sx = x - w / 2 + t * w + random.uniform(-0.6, 0.6)
        a = -math.pi / 2 + (t - 0.5) * 2.4 + random.uniform(-0.2, 0.2)
        c = wiggle(sx, top + 1, a, w * random.uniform(0.45, 0.75),
                   curl=random.uniform(-0.6, 0.6), wav=0.3, ph=random.uniform(0, 6), n=20)
        tents.append(tube(c, w * 0.075, w * 0.05))
    random.shuffle(tents)
    for p in tents: add([p], [p])


# ---------------------------------------------------------------- scene (back to front)
sky()
light_rays()
current()
sea_surface()
island()
shark(125, 112, 0.36, -4)                                   # distant reef shark
for bx, by in ((247, 100), (271, 105), (240, 115), (263, 119), (286, 112), (252, 131), (277, 127)):
    barracuda(bx, by, 0.32, random.uniform(-4, 4))
turtle(193, 124, 0.72, -55)
manta(162, 68, 0.85, 25)
shark(247, 58, 0.75, 6, flip=True)
diver(48, 60, 0.95, -8)
diver(84, 84, 0.8, 4)
dhoni(150, 22.5, 0.55)
seabed()
for rx_, rr in ((70, 8), (232, 7), (152, 5)): rock(rx_, rr)
sea_fan(55, 58)
staghorn(18, 18)
staghorn(286, 16)
staghorn(108, 11, 3)
brain_coral(90, 15, 12)
table_coral(252, 24, 22)
sponges(214)
for gx in (5, 38, 120, 165, 203, 272, 294): seagrass(gx, random.randint(3, 5))
anemone(132, 26)
clownfish(124, 151, 0.6, -10)
clownfish(141, 146, 0.5, 15, flip=True)
stingray(184, 194, 0.6, 80, sy=0.6)
for fx, fy in ((70, 124), (80, 129), (74, 136), (90, 133), (86, 141), (98, 138), (66, 131)):
    reef_fish(fx, fy, 0.75, random.uniform(-8, 8))


# ---------------------------------------------------------------- hidden-line removal + output
def inside(pts, poly):
    x, y = pts[:, :1], pts[:, 1:]
    x1, y1, x2, y2 = poly[:-1, 0], poly[:-1, 1], poly[1:, 0], poly[1:, 1]
    xi = x1 + (y - y1) * (x2 - x1) / np.where(y2 == y1, 1e-12, y2 - y1)
    return (((y1 > y) != (y2 > y)) & (x < xi)).sum(1) % 2 == 1

def hide(objs):
    occ, out = [], []
    for lines, polys in reversed(objs):                      # front to back
        for l in lines:
            pts = resample(l)
            vis = (pts[:, 0] >= 0) & (pts[:, 0] <= W) & (pts[:, 1] >= 0) & (pts[:, 1] <= H)
            lo, hi = pts.min(0), pts.max(0)
            for poly, plo, phi in occ:
                if (plo > hi).any() or (phi < lo).any(): continue
                cand = vis & (pts[:, 0] >= plo[0]) & (pts[:, 0] <= phi[0]) & (pts[:, 1] >= plo[1]) & (pts[:, 1] <= phi[1])
                if cand.any(): vis[cand] &= ~inside(pts[cand], poly)
            out += runs(pts, vis)
        occ += [(p, p.min(0), p.max(0)) for p in polys]
    return out

def rdp(p, eps=0.03):
    keep = np.zeros(len(p), bool); keep[[0, -1]] = True
    stack = [(0, len(p) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1: continue
        d = p[j] - p[i]; seg = p[i + 1:j] - p[i]; L = math.hypot(*d)
        dist = np.abs(d[0] * seg[:, 1] - d[1] * seg[:, 0]) / L if L > 1e-9 else np.hypot(*seg.T)
        k = int(np.argmax(dist))
        if dist[k] > eps:
            keep[i + 1 + k] = True; stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return p[keep]

def order(paths):
    """Greedy nearest-neighbour ordering (with reversal) to cut pen-up travel."""
    starts = np.array([p[0] for p in paths]); ends = np.array([p[-1] for p in paths])
    used = np.zeros(len(paths), bool); pos = np.zeros(2); out = []
    for _ in paths:
        ds = np.hypot(*(starts - pos).T); de = np.hypot(*(ends - pos).T)
        ds[used] = np.inf; de[used] = np.inf
        i, j = int(np.argmin(ds)), int(np.argmin(de))
        p, k = (paths[i], i) if ds[i] <= de[j] else (paths[j][::-1], j)
        used[k] = True; out.append(p); pos = p[-1]
    return out

paths = hide(objects)
paths = [rdp(p) for p in paths if np.hypot(*np.diff(p, axis=0).T).sum() > 0.3]
paths.append(np.array([(0, 0), (W, 0), (W, H), (0, H), (0, 0)]))       # frame
paths = order(paths)

svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}">',
       '<rect width="100%" height="100%" fill="white"/>',
       '<g fill="none" stroke="black" stroke-width="0.3" stroke-linecap="round" stroke-linejoin="round">']
svg += ['<path d="M' + " L".join(f"{x:.2f} {y:.2f}" for x, y in p) + '"/>' for p in paths]
svg += ["</g>", "</svg>"]
open("underwater.svg", "w").write("\n".join(svg) + "\n")
ink = sum(np.hypot(*np.diff(p, axis=0).T).sum() for p in paths)
print(f"{len(paths)} paths, {ink / 1000:.1f} m of ink")
