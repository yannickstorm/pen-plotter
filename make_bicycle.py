#!/usr/bin/env python3
"""Generate bicycle.gcode: a bicycle logo centred in a 50x50 mm box (origin = lower-left)."""
import math

UP, DOWN, FEED, TRAVEL = 0, 35, 2000, 4000
BOX = 50.0

# (kind, params) in an arbitrary design space; centred into the box afterwards
R = (12, 14); F = (38, 14); BB = (23, 13); WR = 11.5
seat = (20, 30); ht_top = (35, 31); ht_bot = (36, 26)
items = [
    ("circle", R, WR), ("circle", F, WR),          # wheels
    ("circle", R, 1.2), ("circle", F, 1.2),        # hubs
    ("circle", BB, 2.5),                           # chainring
    ("poly", [R, BB]),                             # chainstay
    ("poly", [R, seat, BB]),                       # seat stay + seat tube
    ("poly", [seat, ht_top]),                      # top tube
    ("poly", [BB, ht_bot, ht_top]),                # down tube + head tube
    ("poly", [ht_bot, F]),                         # fork
    ("poly", [seat, (19, 34)]),                    # seat post
    ("poly", [(15.5, 35), (22.5, 35)]),            # saddle
    ("poly", [ht_top, (34, 36)]),                  # stem
    ("poly", [(32, 37), (38, 37)]),                # handlebar
    ("poly", [BB, (21, 8.5)]),                     # crank arm
    ("poly", [(19.5, 8.5), (22.5, 8.5)]),          # pedal
]

def bounds():
    xs, ys = [], []
    for it in items:
        if it[0] == "circle":
            (cx, cy), r = it[1], it[2]
            xs += [cx - r, cx + r]; ys += [cy - r, cy + r]
        else:
            xs += [p[0] for p in it[1]]; ys += [p[1] for p in it[1]]
    return min(xs), max(xs), min(ys), max(ys)

x0, x1, y0, y1 = bounds()
size = max(x1 - x0, y1 - y0)
scale = (BOX - 2.0) / size                     # leave a 1 mm margin inside the box
ox = (BOX - (x1 - x0) * scale) / 2 - x0 * scale
oy = (BOX - (y1 - y0) * scale) / 2 - y0 * scale
tx = lambda p: (p[0] * scale + ox, p[1] * scale + oy)

g = [
    "; Bicycle logo, fits a 50x50 mm box, origin X0 Y0 = lower-left of the box",
    f"; pen up = M3 S{UP}, pen down = M3 S{DOWN}",
    "G21", "G90", f"M3 S{UP}",
]
def pen_down(): g.extend([f"M3 S{DOWN}", "G4 P0.4"])
def pen_up():   g.extend([f"M3 S{UP}", "G4 P0.4"])
def goto(p):
    pen_up(); g.append(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F{TRAVEL}")

for it in items:
    if it[0] == "circle":
        c = tx(it[1]); r = it[2] * scale
        goto((c[0] + r, c[1])); pen_down()
        g.append(f"G3 X{c[0] + r:.3f} Y{c[1]:.3f} I{-r:.3f} J0 F{FEED}")   # full CCW circle
    else:
        pts = [tx(p) for p in it[1]]
        goto(pts[0]); pen_down()
        g.extend(f"G1 X{p[0]:.3f} Y{p[1]:.3f} F{FEED}" for p in pts[1:])
pen_up(); g.append(f"G1 X0 Y0 F{TRAVEL}")

open("bicycle.gcode", "w").write("\n".join(g) + "\n")
print(f"scale {scale:.3f}, {len(g)} lines")
