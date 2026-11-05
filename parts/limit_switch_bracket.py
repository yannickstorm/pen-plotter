"""Adjustable limit-switch bracket: a fixed ARM on the motor and a sliding CARRIER that holds the two switches (mm).

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin; Z is up.
The "front" screw is the one on the side the X lever points to: (X_DIR * HOLE_SPACING/2, 0).

  ARM      base on the motor screws, a post, a diagonal beam and a clamp pad with two slots along X.
  CARRIER  upper shelf (X switch, shelf top at X_Z), lower shelf 10 mm below (Y switch) and a plate that
           lies on the arm's clamp pad, with two slots along Y. Two M3 screws go through each pair of
           crossing slots, so the carrier slides +-ADJ in X and Y and clamps anywhere in between.
Nominal switch-stack position: STACK_DX along X and STACK_DY (sign Y_SIGN) along Y from the front screw.
  * X switch: its LONG side (the clicking side) faces +X;  Y switch: its long side faces -Y.
Fit the lower (Y) switch first: its screws are reached through access holes in the upper shelf.

Run:  python limit_switch_bracket.py
      -> limit_switch_arm.step/.stl, limit_switch_carrier.step/.stl, limit_switch_assembly.stl (preview only)
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
HEAD_D = 6.0               # M3 cap/pan head
BASE_T = 4.0
BASE_W = 12.0
POST = 14.0                # square post between the motor screws
# --- where the switches go (nominal; the carrier slides +-ADJ around this) ---
X_DIR = 1                  # +1: front screw / X lever on the +X side (-1 mirrors the whole part)
STACK_DX = 50.0            # from the front screw, along the lever direction
STACK_DY = 40.0            # from the front screw, sideways (sign below)
Y_SIGN = -1                # -1: stack on the -Y side
X_Z = 35.0                 # top of the X (upper) shelf above the motor face
Y_DROP = 10.0              # Y shelf top is this much lower
TOP_T = 3.0                # thickness of the carrier's upper plate and of the arm
Y_SHELF_T = 4.0
BEAM_W = 12.0
WEB_T = 2.5
# --- clamp: two M3 screws through crossing slots ---
ADJ = 10.0                 # carrier slides +-ADJ mm in X and in Y
SLOT_W = 3.4               # M3 clearance
SO = 6.0                   # the two screws sit SO mm either side of the clamp centre
CLAMP_DIST = 52.0          # clamp centre this far back from the stack, along the arm
EDGE = 3.0                 # plate margin around the slots
# --- micro switch (1 A 125 V AC type, photo dims): long side 12.8 with the lever on it, 6.2 deep from the
# clicking side to the back (3 solder pins stick out of the back), 5.8 thick (assumed, measure it);
# 2 holes dia 2.0, 6.5 apart along the long side, through the thickness ---
SW_L, SW_W, SW_H = 12.8, 6.2, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.7              # pilot for an M2 self-tapping screw (switch holes are dia 2.0)
SCREW_HEAD = 4.4           # hole in the upper shelf for the lower switch's M2 screw heads
WIRE_GAP = 6.0             # free space behind the lower switch for its solder pins and wires
PIN_Z, PIN_LEN = SW_H / 2, 3.5
PAD = 3.0
FILLET = 1.0

Y_Z = X_Z - Y_DROP
ARM_TOP = X_Z - TOP_T      # the carrier plate lies on the arm
assert Y_Z + SW_H + 0.3 < ARM_TOP, "lower switch would touch the upper shelf"
assert POST / 2 + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2, "post collides with screw heads"

def rounded(solid, r=FILLET):
    return fillet(solid.edges().filter_by(Axis.Z), r)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return rounded(Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0), r)

def strip(p0, p1, half_w, z0, z1):
    """Straight plate of width 2*half_w between two points."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy); nx, ny = -dy / d, dx / d
    pts = [(p0[0] - half_w * nx, p0[1] - half_w * ny), (p1[0] - half_w * nx, p1[1] - half_w * ny),
           (p1[0] + half_w * nx, p1[1] + half_w * ny), (p0[0] + half_w * nx, p0[1] + half_w * ny)]
    return extrude(Plane.XY.offset(z0) * Polygon(*pts, align=None), amount=z1 - z0)

def slot(cx, cy, z, length, along_x, depth):
    """Slot of overall `length` x SLOT_W, cut through `depth`."""
    f = SlotCenterToCenter(length - SLOT_W, SLOT_W)
    if not along_x:
        f = Rot(0, 0, 90) * f
    return Pos(cx, cy, z) * extrude(f, amount=depth, both=True)

# nominal stack centre and the clamp centre behind it (built for X_DIR=+1, mirrored at the end)
sx = HOLE_SPACING / 2 + STACK_DX
sy = Y_SIGN * STACK_DY
L = math.hypot(sx, sy)
ux, uy = sx / L, sy / L
cx, cy = sx - CLAMP_DIST * ux, sy - CLAMP_DIST * uy
slot_len = 2 * ADJ + SLOT_W

# ------------------------------------------------------------------ ARM
def build_arm():
    base = slab(-(HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4), HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)
    post = Pos(0, 0, ARM_TOP / 2) * Box(POST, POST, ARM_TOP)
    z0 = ARM_TOP - TOP_T
    beam = strip((0, 0), (cx, cy), BEAM_W / 2, z0, ARM_TOP)
    pad_hw = SO + ADJ + SLOT_W / 2 + EDGE          # x half-width: the X slots
    pad_hh = SO + SLOT_W / 2 + EDGE                # y half-height
    pad = slab(cx - pad_hw, cx + pad_hw, cy - pad_hh, cy + pad_hh, z0, ARM_TOP)
    arm = base + post + beam + pad
    # vertical web under the beam, standing on the bed, sloped end
    Larm = math.hypot(cx, cy)
    web_top, web_foot = Larm - 6.0, min(24.0, Larm * 0.6)
    prof = Polygon((0, 0), (web_foot, 0), (web_top, z0), (0, z0), align=None)
    arm += Rot(0, 0, math.degrees(math.atan2(cy, cx))) * extrude(Plane.XZ * prof, WEB_T / 2, both=True)
    # motor screws
    for k in (-1, 1):
        arm -= Pos(k * HOLE_SPACING / 2, 0, BASE_T / 2) * Cylinder(MOTOR_SCREW / 2, BASE_T + 2)
    # two slots along X: screw 1 at (cx-SO, cy+SO), screw 2 at (cx+SO, cy-SO), each free to move +-ADJ
    arm -= slot(cx - SO, cy + SO, ARM_TOP - TOP_T / 2, slot_len, True, TOP_T + 2)
    arm -= slot(cx + SO, cy - SO, ARM_TOP - TOP_T / 2, slot_len, True, TOP_T + 2)
    return arm

# ------------------------------------------------------------------ CARRIER
def build_carrier():
    # upper shelf: front edge flush with the X switch's +X face, margin behind and to the sides
    x_lo, x_hi = sx - SW_L / 2 - PAD, sx + SW_W / 2
    wall_y1 = sy + SW_W / 2 + WIRE_GAP + PAD
    y_lo, y_hi = sy - SW_L / 2 - PAD, max(sy + SW_L / 2 + PAD, wall_y1)
    upper = slab(x_lo, x_hi, y_lo, y_hi, X_Z - TOP_T, X_Z)
    # plate that lies on the arm's clamp pad, with the connecting strip to the shelf
    clamp = slab(cx - SO - SLOT_W / 2 - EDGE, cx + SO + SLOT_W / 2 + EDGE,
                 cy - SO - ADJ - SLOT_W / 2 - EDGE, cy + SO + ADJ + SLOT_W / 2 + EDGE, X_Z - TOP_T, X_Z)
    link = strip((cx, cy), (sx, sy), 7.0, X_Z - TOP_T, X_Z)
    # lower shelf for the Y switch (long side faces -Y), wall behind it with room for the solder pins
    low = slab(sx - SW_L / 2 - PAD, sx + SW_L / 2 + PAD, sy - SW_W / 2, wall_y1, Y_Z - Y_SHELF_T, Y_Z)
    wall_y0 = sy + SW_W / 2 + WIRE_GAP
    wall = Pos((x_lo + x_hi) / 2, (wall_y0 + wall_y1) / 2, ((Y_Z - Y_SHELF_T) + (X_Z - TOP_T / 2)) / 2) * \
        Box(x_hi - x_lo, wall_y1 - wall_y0, (X_Z - TOP_T / 2) - (Y_Z - Y_SHELF_T))
    car = upper + clamp + link + low + wall
    # slots along Y that cross the arm's slots
    car -= slot(cx - SO, cy + SO, X_Z - TOP_T / 2, slot_len, False, TOP_T + 2)
    car -= slot(cx + SO, cy - SO, X_Z - TOP_T / 2, slot_len, False, TOP_T + 2)
    # X switch pilot holes (along Y); Y switch pilot holes (along X) with access holes above them
    for k in (-1, 1):
        car -= Pos(sx, sy + k * SW_HOLE_SPACING / 2, X_Z - TOP_T / 2) * Cylinder(SW_HOLE / 2, TOP_T + 2)
        xx = sx + k * SW_HOLE_SPACING / 2
        car -= Pos(xx, sy, Y_Z - Y_SHELF_T / 2) * Cylinder(SW_HOLE / 2, Y_SHELF_T + 2)
        car -= Pos(xx, sy, X_Z - TOP_T / 2) * Cylinder(SCREW_HEAD / 2, TOP_T + 2)
    return car

arm, carrier = build_arm(), build_carrier()

# ------------------------------------------------------------------ clearance check over the whole sliding range
y_body = Pos(sx, sy, Y_Z + SW_H / 2) * Box(SW_L, SW_W, SW_H)                            # lower switch
y_pins = Pos(sx, sy + SW_W / 2 + PIN_LEN / 2, Y_Z + PIN_Z) * Box(SW_L, PIN_LEN, 1.5)    # its solder pins
worst = 0.0
for dx in (-ADJ, 0, ADJ):
    for dy in (-ADJ, 0, ADJ):
        m = Pos(dx, dy, 0)
        for item in (carrier, y_body, y_pins):
            try:
                v = (arm & (m * item)).volume
            except Exception:
                v = 0.0
            worst = max(worst, v)
assert worst < 1e-3, f"arm and carrier/switch collide somewhere in the sliding range ({worst:.1f} mm3)"

if X_DIR < 0:
    arm, carrier = mirror(arm, Plane.YZ), mirror(carrier, Plane.YZ)

d = abs(HOLE_SPACING / 2 * uy)
print(f"web-to-front-screw clearance: {d - WEB_T / 2 - HEAD_D / 2:.1f} mm")
for name, p in (("arm", arm), ("carrier", carrier)):
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"stack nominal ({sx:.1f}, {sy:.1f}); slides +-{ADJ:g} mm; clamp centre ({cx:.1f}, {cy:.1f}); arm/carrier overlap max {worst:.4f} mm3")
export_step(arm, "limit_switch_arm.step"); export_stl(arm, "limit_switch_arm.stl")
export_step(carrier, "limit_switch_carrier.step"); export_stl(carrier, "limit_switch_carrier.stl")
export_stl(Compound([arm, carrier]), "limit_switch_assembly.stl")
