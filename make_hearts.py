#!/usr/bin/env python3
"""Generate amandine_yannick.gcode: the two names in script inside a big heart,
with little hearts around, centred in a 50x50 mm box (origin = lower-left).

Needs the Hershey single-stroke fonts:  pip install Hershey-Fonts
"""
import math
from HersheyFonts import HersheyFonts

UP, DOWN, FEED, TRAVEL = 0, 35, 2000, 4000
BOX = 50.0
FONT = "scripts"            # single-stroke script, ideal for a pen

paths = []                  # list of polylines in an arbitrary design space (mm-ish)

def heart(cx, cy, size, n=120):
    """Classic parametric heart, width ~= size, starting/ending at the bottom tip."""
    k = size / 32.0
    pts = []
    for i in range(n + 1):
        t = math.pi + 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * k, cy + y * k))
    return pts

def text(s, cx, cy, height):
    """Single-stroke text centred on (cx, cy)."""
    f = HersheyFonts(); f.load_default_font(FONT); f.normalize_rendering(height)
    strokes = [list(st) for st in f.strokes_for_text(s)]
    xs = [p[0] for st in strokes for p in st]; ys = [p[1] for st in strokes for p in st]
    dx = cx - (min(xs) + max(xs)) / 2; dy = cy - (min(ys) + max(ys)) / 2
    return [[(x + dx, y + dy) for x, y in st] for st in strokes]

# big double-outlined heart framing everything
paths.append(heart(0, 0, 48))
paths.append(heart(0, 0.6, 44))
# names + a little heart between them
paths += text("Amandine", 0, 4.2, 6.5)
paths.append(heart(0, -2.3, 4.5))
paths += text("Yannick", 1.2, -8.3, 6.2)
# tiny hearts in the lobes and around the outside
for cx, cy, s in [(-10, 11, 3.5), (10, 11, 3.5), (-23, -14, 4), (23, -14, 4), (-21, -21, 2.5), (21, -21, 2.5)]:
    paths.append(heart(cx, cy, s))

# --- fit into the box -------------------------------------------------------
xs = [p[0] for pl in paths for p in pl]; ys = [p[1] for pl in paths for p in pl]
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
scale = (BOX - 2.0) / max(x1 - x0, y1 - y0)    # leave a 1 mm margin inside the box
ox = (BOX - (x1 - x0) * scale) / 2 - x0 * scale
oy = (BOX - (y1 - y0) * scale) / 2 - y0 * scale
paths = [[(x * scale + ox, y * scale + oy) for x, y in pl] for pl in paths]

# --- G-code -----------------------------------------------------------------
g = [
    "; Amandine & Yannick in a heart, fits a 50x50 mm box, origin X0 Y0 = lower-left of the box",
    f"; pen up = M3 S{UP}, pen down = M3 S{DOWN}",
    "G21", "G90", f"M3 S{UP}",
]
def pen_down(): g.extend([f"M3 S{DOWN}", "G4 P0.4"])
def pen_up():   g.extend([f"M3 S{UP}", "G4 P0.4"])

pos = None
for pl in paths:
    if len(pl) < 2:
        continue
    if pos is None or math.dist(pos, pl[0]) > 0.05:   # only lift when the next stroke is elsewhere
        pen_up(); g.append(f"G1 X{pl[0][0]:.3f} Y{pl[0][1]:.3f} F{TRAVEL}"); pen_down()
    g.extend(f"G1 X{x:.3f} Y{y:.3f} F{FEED}" for x, y in pl[1:])
    pos = pl[-1]
pen_up(); g.append(f"G1 X0 Y0 F{TRAVEL}")

open("amandine_yannick.gcode", "w").write("\n".join(g) + "\n")
print(f"scale {scale:.3f}, {len(paths)} strokes, {len(g)} lines")
