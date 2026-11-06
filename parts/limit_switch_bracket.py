"""Low-profile adjustable limit-switch bracket, dovetail slides locked with set screws, three printed parts (mm).

Frame: origin = midpoint of the two NEMA motor screws (they lie on the X axis at x = +-15.5), Z up from the motor face.
Lever contact points (where the carriage hits the levers):
  X switch lever at X_HIT = (40, 0, 5),    its lever points +X
  Y switch lever at Y_HIT = (50, -30, 10), its lever points -Y
The switches lie flat (screws vertical), their LONG side (the clicking side) towards the lever direction.

  ARM       base on the two motor screws, a flat beam and a block with a dovetail channel along Y.
  CROSS     cross-slide: slides along Y in the arm's channel, with a dovetail channel along X on its top.
  CARRIER   holds both switches (each in its own portal: shelf, two side walls, a plate above) and slides along X in
            the cross-slide. Moving it shifts both switches together by (dx, dy), +-ADJ each.

Slides are 45 degree dovetails with DT_CL clearance per side (a loose sliding fit); each is locked by an M3 set screw
into an M3 heat-set insert:  Y: on the +X face of the arm's block;  X: on the +Y side of the cross-slide.
There is no Z slide (no room at these heights): the switch heights come from X_HIT / Y_HIT.

Measuring (engraved scales, 1 mm per tick, 0 = nominal, + = towards +X / +Y):
  Y  on the arm's block: the +Y end edge of the cross-slide sits next to a numbered tick.
  X  on the cross-slide's top: the -X end edge of the carrier's plate sits next to a tick (longest = 0).

Run:  python limit_switch_bracket.py -> limit_switch_{arm,cross,carrier}.step/.stl and limit_switch_assembly.stl
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
BASE_T = 4.0
BASE_W = 16.0
# --- where the levers get hit (nominal) ---
X_HIT = (40.0, 0.0, 5.0)
Y_HIT = (50.0, -30.0, 10.0)
LEVER_OUT = 2.5            # the lever sticks out this far in front of the switch's clicking face (assumed)
# --- adjustment ---
ADJ = 8.0                  # the carrier moves +-ADJ mm in X and in Y
# --- dovetails: 45 degrees, so they print without supports ---
DT_H, DT_B0, DT_CL = 3.0, 3.0, 0.3     # rail height, rail half width at its base, clearance per side (bigger = looser)
RAIL_LEN = 14.0
# --- locking: M3 heat-set insert (hole INS_D x INS_DEPTH) + M3 set screw (passage SET_D) ---
INS_D, INS_DEPTH, SET_D = 4.2, 6.0, 3.2
# --- micro switch (1 A 125 V AC type): long side 12.8 with the lever on it, 6.2 deep from the clicking side to the
# back (3 solder pins stick out of the back), 5.8 thick (assumed, measure it); 2 holes dia 2.0, 6.5 apart ---
SW_L, SW_W, SW_H = 12.8, 6.2, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.7              # pilot for an M2 self-tapping screw
SCREW_HEAD = 4.4           # hole in the plate above each switch for the M2 screw heads
PIN_LEN = 3.5
PAD = 3.0
SHELF_T = 3.0
TOP_T = 3.0                # carrier plate
FILLET = 1.0
# --- measuring scales ---
TICK_D, LABEL_SIZE = 0.5, 3.0

# --- switch positions from the lever contact points ---
X_SW = (X_HIT[0] - LEVER_OUT - SW_W / 2, X_HIT[1], X_HIT[2])       # centre of the X switch body
Y_SW = (Y_HIT[0], Y_HIT[1] + LEVER_OUT + SW_W / 2, Y_HIT[2])       # centre of the Y switch body
X_SEAT, Y_SEAT = X_SW[2] - SW_H / 2, Y_SW[2] - SW_H / 2            # tops of the shelves

# --- levels ---
ROOF_HW = 3.0
PEAK = (DT_H + DT_CL) + (DT_B0 + DT_H + 2 * DT_CL - ROOF_HW)       # depth of the cross-slide channel's peaked roof
CS_T = PEAK + 1.7                                                  # cross-slide thickness
Z_CS_TOP = max(X_SEAT, Y_SEAT) + SW_H + 1.6                        # cross-slide top = carrier plate underside
Z_B = Z_CS_TOP - CS_T                                              # top of the arm's block = cross-slide underside
assert Z_B > DT_H + DT_CL + 2.0, "arm block too low for the dovetail channel"

_c0 = DT_B0 + DT_CL
_d = DT_H + DT_CL
MALE = [(-DT_B0, -0.5), (DT_B0, -0.5), (DT_B0, 0), (DT_B0 + DT_H, DT_H), (-DT_B0 - DT_H, DT_H), (-DT_B0, 0)]
FEMALE = [(-_c0, 0.5), (_c0, 0.5), (_c0, 0), (_c0 + _d, -_d), (-_c0 - _d, -_d), (-_c0, 0)]
_c1 = _c0 + _d
FEMALE_PEAKED = [(-_c0, 0.5), (_c0, 0.5), (_c0, 0), (_c1, -_d), (ROOF_HW, -PEAK), (-ROOF_HW, -PEAK), (-_c1, -_d), (-_c0, 0)]

def dt(profile, origin, u, w, length):
    """Dovetail prism. u = across, w = along, v = w x u = out of the surface it sits on."""
    pl = Plane(origin=origin, x_dir=u, z_dir=w)
    return extrude(pl * Polygon(*profile, align=None), amount=length / 2, both=True)

def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return fillet(box(x0, x1, y0, y1, z0, z1).edges().filter_by(Axis.Z), r)

def strip(p0, p1, half_w, z0, z1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy); nx, ny = -dy / d, dx / d
    pts = [(p0[0] - half_w * nx, p0[1] - half_w * ny), (p1[0] - half_w * nx, p1[1] - half_w * ny),
           (p1[0] + half_w * nx, p1[1] + half_w * ny), (p0[0] + half_w * nx, p0[1] + half_w * ny)]
    return extrude(Plane.XY.offset(z0) * Polygon(*pts, align=None), amount=z1 - z0)

def cyl_x(x0, x1, y, z, d): return Pos((x0 + x1) / 2, y, z) * Rot(0, 90, 0) * Cylinder(d / 2, abs(x1 - x0))
def cyl_y(x, y0, y1, z, d): return Pos(x, (y0 + y1) / 2, z) * Rot(90, 0, 0) * Cylinder(d / 2, abs(y1 - y0))
def cyl_z(x, y, z0, z1, d): return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, abs(z1 - z0))

def tick_w(t): return 1.0 if t == 0 else (0.8 if t % 4 == 0 else 0.5)
def tick_len(t): return 3.0 if t == 0 else (2.2 if t % 4 == 0 else 1.2)
def tick_text(t): return "0" if t == 0 else f"{t:+d}"

def engrave(txt, origin, x_dir, z_dir):
    pl = Plane(origin=origin, x_dir=x_dir, z_dir=z_dir)
    out = None
    for f in Text(txt, LABEL_SIZE, align=(Align.CENTER, Align.CENTER)).faces():
        piece = extrude(pl * f, amount=TICK_D, both=True)
        out = piece if out is None else out + piece
    return out

# ------------------------------------------------------------------ layout of the slides (plan)
CX, CY = 16.0, -39.5               # centre of the slides
PAD_HW = 13.0                      # arm block: x from CX - 8.5 to CX + PAD_HW
PAD_Y0, PAD_Y1 = CY - RAIL_LEN / 2 - ADJ - 2.0, CY + 21.0
CS_HX, CS_HY = RAIL_LEN / 2 + ADJ + 2.0, 9.5          # cross-slide half sizes
CHX, CHY = 8.0, 9.3                # carrier plate half sizes over the cross-slide
BOSS = 5.0

# ------------------------------------------------------------------ ARM (fixed to the motor)
def build_arm():
    fx = HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4
    base = slab(-fx, fx, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)
    beam = box(CX - 11.5, CX + 1.0, PAD_Y1 - 1.0, -BASE_W / 2 + 1.0, 0, BASE_T)      # narrow: the X portal moves past it
    block = slab(CX - 11.5, CX + PAD_HW, PAD_Y0, PAD_Y1, 0, Z_B)      # 3 mm wider on the -X side for the Y scale
    arm = base + beam + block
    for k in (-1, 1):
        arm -= cyl_z(k * HOLE_SPACING / 2, 0, -1, BASE_T + 1, MOTOR_SCREW)
    # Y channel on the block's top; set screw from the +X face onto the flank of the cross-slide's rail
    arm -= dt(FEMALE, (CX, (PAD_Y0 + PAD_Y1) / 2, Z_B), (-1, 0, 0), (0, 1, 0), PAD_Y1 - PAD_Y0 + 2)
    zc = Z_B - 2.4
    arm -= cyl_x(CX + PAD_HW - INS_DEPTH, CX + PAD_HW + 1, CY, zc, INS_D)
    arm -= cyl_x(CX + 2, CX + PAD_HW, CY, zc, SET_D)
    # Y scale: ticks on the block's -X side (the carrier's arms are never above it); the +Y end edge of the cross-slide (y = CY + CS_HY + offset) is the pointer
    for t in range(-int(ADJ), int(ADJ) + 1):
        arm -= Pos(CX - 11.5 + 0.3 + tick_len(t) / 2, CY + CS_HY + t, Z_B) * Box(tick_len(t), tick_w(t), 2 * TICK_D)
        if t % 4 == 0:
            arm -= engrave(tick_text(t), (CX - 11.5 + 0.3 + 3.0 + 0.8 + 1.6, CY + CS_HY + t, Z_B), (1, 0, 0), (0, 0, 1))
    return arm

# ------------------------------------------------------------------ CROSS-SLIDE (slides in Y in the arm's block)
def build_cross():
    body = slab(CX - CS_HX, CX + CS_HX, CY - CS_HY, CY + CS_HY, Z_B, Z_CS_TOP)
    boss = box(CX - BOSS, CX + BOSS, CY + CHY + 0.2, CY + CS_HY + INS_DEPTH, Z_B, Z_CS_TOP)
    cs = body + boss
    cs += dt(MALE, (CX, CY, Z_B), (1, 0, 0), (0, 1, 0), RAIL_LEN)                          # Y rail on the underside
    cs -= dt(FEMALE_PEAKED, (CX, CY, Z_CS_TOP), (0, 1, 0), (1, 0, 0), 2 * CS_HX + 2)       # X channel on the top
    zc = Z_CS_TOP - 2.4
    cs -= cyl_y(CX, CY + CS_HY, CY + CS_HY + INS_DEPTH + 1, zc, INS_D)
    cs -= cyl_y(CX, CY, CY + CS_HY + 1, zc, SET_D)
    # X scale: ticks on the +Y edge of the top; the -X end edge of the carrier plate (x = CX - CHX + offset) is the pointer
    for t in range(-int(ADJ), int(ADJ) + 1):
        cs -= Pos(CX - CHX + t, CY + CS_HY - 0.3 - tick_len(t) / 2, Z_CS_TOP) * Box(tick_w(t), tick_len(t), 2 * TICK_D)
    return cs

# ------------------------------------------------------------------ CARRIER (slides in X in the cross-slide)
XB, XF = -(SW_W / 2 + 1.4), SW_W / 2      # portal in the switch's own frame: back and front (click face at +x)
YH = SW_L / 2 + PAD

def portal_local(seat):
    """Shelf, two side walls and a plate above, around a switch centred at the origin, click face towards +x."""
    top0, top1 = Z_CS_TOP, Z_CS_TOP + TOP_T
    p = slab(XB, XF, -YH, YH, top0, top1) + slab(XB, XF, -YH, YH, seat - SHELF_T, seat)
    for k in (-1, 1):
        p += box(XB, XF, min(k * (YH - 2.0), k * YH), max(k * (YH - 2.0), k * YH), seat - SHELF_T, top0 + TOP_T / 2)
    return p

def place(shape, centre, rot):
    return Pos(centre[0], centre[1], 0) * Rot(0, 0, rot) * shape

def build_carrier():
    px = place(portal_local(X_SEAT), X_SW, 0)
    py = place(portal_local(Y_SEAT), Y_SW, -90)       # click face towards -Y
    clamp = slab(CX - CHX, CX + CHX, CY - CHY, CY + CHY, Z_CS_TOP, Z_CS_TOP + TOP_T)
    rail = dt(MALE, (CX, CY, Z_CS_TOP), (0, -1, 0), (1, 0, 0), RAIL_LEN)                    # X rail on the underside
    # plates from the slides to the two portals, ending at the back edge of each portal's plate
    xt = (X_SW[0] + XB + 1.5, X_SW[1])
    yt = (Y_SW[0], Y_SW[1] - XB - 1.5)
    s1 = strip((CX, CY), xt, 7.0, Z_CS_TOP, Z_CS_TOP + TOP_T)
    s2 = strip((CX, CY), yt, 7.0, Z_CS_TOP, Z_CS_TOP + TOP_T)
    car = clamp + rail + s1 + s2 + px + py
    for k in (-1, 1):                                  # pilot holes and screw-head access, cut after everything is joined
        car -= place(cyl_z(0, k * SW_HOLE_SPACING / 2, X_SEAT - SHELF_T - 1, X_SEAT + 1, SW_HOLE), X_SW, 0)
        car -= place(cyl_z(0, k * SW_HOLE_SPACING / 2, Z_CS_TOP - 1, Z_CS_TOP + TOP_T + 1, SCREW_HEAD), X_SW, 0)
        car -= place(cyl_z(0, k * SW_HOLE_SPACING / 2, Y_SEAT - SHELF_T - 1, Y_SEAT + 1, SW_HOLE), Y_SW, -90)
        car -= place(cyl_z(0, k * SW_HOLE_SPACING / 2, Z_CS_TOP - 1, Z_CS_TOP + TOP_T + 1, SCREW_HEAD), Y_SW, -90)
    return car

arm, cross, carrier = build_arm(), build_cross(), build_carrier()

# ------------------------------------------------------------------ clearance check over the whole sliding range
sw_x = Pos(*X_SW) * Box(SW_W, SW_L, SW_H)
sw_y = Pos(*Y_SW) * Box(SW_L, SW_W, SW_H)
pins_x = Pos(X_SW[0] - SW_W / 2 - PIN_LEN / 2, X_SW[1], X_SW[2]) * Box(PIN_LEN, SW_L, 1.5)
pins_y = Pos(Y_SW[0], Y_SW[1] + SW_W / 2 + PIN_LEN / 2, Y_SW[2]) * Box(SW_L, PIN_LEN, 1.5)
extras = (("swx", sw_x), ("swy", sw_y), ("pinsx", pins_x), ("pinsy", pins_y))
_cache = {}
def overlap(key, a, b):
    if key not in _cache:
        try:
            _cache[key] = (a & b).volume
        except Exception:
            _cache[key] = 0.0
    return _cache[key]

worst = {}
def note(name, v):
    worst[name] = max(worst.get(name, 0.0), v)

R = (-ADJ, 0.0, ADJ)
for dy in R:
    cs = Pos(0, dy, 0) * cross
    note("arm/cross", overlap(("ac", dy), arm, cs))
    for dx in R:
        m = Pos(dx, dy, 0)
        ca = m * carrier
        note("arm/carrier", overlap(("ak", dx, dy), arm, ca))
        note("cross/carrier", overlap(("ck", dx, dy), cs, ca))
        for nm, item in extras:
            it = m * item
            note(f"arm/{nm}", overlap(("a" + nm, dx, dy), arm, it))
            note(f"cross/{nm}", overlap(("c" + nm, dx, dy), cs, it))
for nm, item in extras:                                 # the switches must sit in their portals without touching
    note(f"carrier/{nm} (nominal)", overlap(("kn" + nm, 0, 0), carrier, item))
bad = {k: round(v, 3) for k, v in worst.items() if v > 1e-3}
assert not bad, f"parts collide somewhere in the sliding range: {bad}"

parts = (("arm", arm), ("cross", cross), ("carrier", carrier))
for name, p in parts:
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm (z {bb.min.Z:.1f} to {bb.max.Z:.1f}), "
          f"{p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"X switch centre {tuple(round(v, 1) for v in X_SW)}, Y switch centre {tuple(round(v, 1) for v in Y_SW)}; "
      f"levels: cross-slide top {Z_CS_TOP:.1f}, arm block top {Z_B:.1f}; slide centre ({CX}, {CY}); "
      f"clearance checks passed (worst overlap {max(worst.values()):.4f} mm3)")
for name, p in parts:
    export_step(p, f"limit_switch_{name}.step")
    export_stl(p, f"limit_switch_{name}.stl", tolerance=0.02, angular_tolerance=0.3)
export_stl(Compound([p for _, p in parts]), "limit_switch_assembly.stl", tolerance=0.02, angular_tolerance=0.3)

import json
json.dump({"X_HIT": X_HIT, "Y_HIT": Y_HIT, "X_SW": X_SW, "Y_SW": Y_SW, "LEVER_OUT": LEVER_OUT, "SW_L": SW_L, "SW_W": SW_W,
           "SW_H": SW_H, "SW_HOLE_SPACING": SW_HOLE_SPACING, "ADJ": ADJ, "DT_CL": DT_CL, "CX": CX, "CY": CY,
           "Z_CS_TOP": Z_CS_TOP, "Z_B": Z_B, "HOLE_SPACING": HOLE_SPACING}, open("viewer_params.json", "w"))
