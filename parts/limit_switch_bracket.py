"""Adjustable limit-switch bracket in three printed parts (all dimensions in mm):

  ARM      base on the motor screws and a post with two vertical slots (Z adjustment).
  BRIDGE   a plate that bolts to the post through those slots, a beam and a clamp pad with two slots along Y.
           Slide it up and down on the post: this moves the whole switch stack in Z.
  CARRIER  upper shelf (X switch, shelf top at X_Z), lower shelf 10 mm below (Y switch) and a plate that lies on
           the bridge's pad, with two slots along X. Two M3 screws through the crossing slots clamp it anywhere
           +-ADJ in X and Y.

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin; Z is up. The "front" screw is the one
on the side the X lever points to: (X_DIR * HOLE_SPACING/2, 0).
Nominal switch-stack position: STACK_DX along X and STACK_DY (sign Y_SIGN) along Y from the front screw, X shelf
top at X_Z. It slides +-ADJ in X and Y and +-ADJ_Z in Z.
  * X switch: its LONG side (the clicking side) faces +X;  Y switch: its long side faces -Y.
Fit the lower (Y) switch first: its screws are reached through access holes in the upper shelf.

Run:  python limit_switch_bracket.py
      -> limit_switch_{arm,bridge,carrier}.step/.stl and limit_switch_assembly.stl (preview only)
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
HEAD_D = 6.0               # M3 cap/pan head
BASE_T = 4.0
BASE_W = 16.0               # as wide as the post, so the arm can lie flat on its side when printed
POST_X, POST_Y = 14.0, 16.0   # post between the motor screws
# --- where the switches go (nominal; the carrier slides +-ADJ around this) ---
X_DIR = 1                  # +1: front screw / X lever on the +X side (-1 mirrors the whole part)
STACK_DX = 50.0            # from the front screw, along the lever direction
STACK_DY = 40.0            # from the front screw, sideways (sign below)
Y_SIGN = -1                # -1: stack on the -Y side
X_Z = 35.0                 # top of the X (upper) shelf above the motor face
Y_DROP = 10.0              # Y shelf top is this much lower
TOP_T = 3.0                # thickness of the carrier's upper plate and of the arm
Y_SHELF_T = 4.0
BEAM_W = 10.0
WEB_T = 2.5
# --- clamp: two M3 screws through crossing slots ---
ADJ = 8.0                  # carrier slides +-ADJ mm in X and in Y
ADJ_Z = 8.0                # bridge (and the whole stack) slides +-ADJ_Z mm in Z
PLATE_T = 3.0              # bridge plate against the post
ZS_Y = 4.5                 # the two vertical slots sit this far either side of the post centre
SPZ = 10.0                 # two screws per vertical slot, this far apart
SLOT_W = 3.4               # M3 clearance
SO = 6.0                   # the two screws sit SO mm either side of the clamp centre
CLAMP_DIST = 36.0          # clamp centre this far back from the stack, along the arm
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
assert POST_X / 2 + PLATE_T + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2 + 3, "post collides with screw heads"
PLATE_H = SPZ + SLOT_W + 2 * EDGE
PLATE_BOT = ARM_TOP - PLATE_H
assert PLATE_BOT - ADJ_Z >= BASE_T + 0.3, "bridge plate would hit the base at its lowest position"
POST_H = ARM_TOP + ADJ_Z

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

def zslot(y, zc, length, depth):
    """Vertical slot (overall `length`) cut through the post along X."""
    h = length - SLOT_W
    body = Box(depth, SLOT_W, h)
    for k in (-1, 1):
        body += Pos(0, 0, k * h / 2) * Rot(0, 90, 0) * Cylinder(SLOT_W / 2, depth)
    return Pos(0, y, zc) * body

# nominal stack centre and the clamp centre behind it (built for X_DIR=+1, mirrored at the end)
sx = HOLE_SPACING / 2 + STACK_DX
sy = Y_SIGN * STACK_DY
L = math.hypot(sx, sy)
ux, uy = sx / L, sy / L
cx, cy = sx - CLAMP_DIST * ux, sy - CLAMP_DIST * uy
slot_len = 2 * ADJ + SLOT_W

# ------------------------------------------------------------------ ARM (fixed to the motor)
z_lo0 = PLATE_BOT + EDGE + SLOT_W / 2          # lowest screw of the bridge at nominal height
z_hi0 = z_lo0 + SPZ

def build_arm():
    base = slab(-(HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4), HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)
    post = Pos(0, 0, BASE_T + (POST_H - BASE_T) / 2) * Box(POST_X, POST_Y, POST_H - BASE_T)
    arm = base + post
    for k in (-1, 1):
        arm -= Pos(k * HOLE_SPACING / 2, 0, BASE_T / 2) * Cylinder(MOTOR_SCREW / 2, BASE_T + 2)
    # two vertical slots through the post (M3 screws along X, nuts on the -X face)
    zs0, zs1 = z_lo0 - ADJ_Z - SLOT_W / 2, z_hi0 + ADJ_Z + SLOT_W / 2
    for y in (-ZS_Y, ZS_Y):
        arm -= zslot(y, (zs0 + zs1) / 2, zs1 - zs0, POST_X + 2)
    return arm

# ------------------------------------------------------------------ BRIDGE (slides in Z on the post)
def build_bridge():
    z0 = ARM_TOP - TOP_T
    ph = ZS_Y + SLOT_W / 2 + EDGE
    plate = Pos(POST_X / 2 + PLATE_T / 2, 0, PLATE_BOT + PLATE_H / 2) * Box(PLATE_T, 2 * ph, PLATE_H)
    beam = strip((POST_X / 2 + PLATE_T / 2, -(ph - EDGE)), (cx, cy), BEAM_W / 2, z0, ARM_TOP)
    pad_hx = SO + SLOT_W / 2 + EDGE
    pad_hy = SO + ADJ + SLOT_W / 2 + EDGE
    pad = slab(cx - pad_hx, cx + pad_hx, cy - pad_hy, cy + pad_hy, z0, ARM_TOP)
    br = plate + beam + pad
    for y in (-ZS_Y, ZS_Y):
        for z in (z_lo0, z_hi0):
            br -= Pos(POST_X / 2 + PLATE_T / 2, y, z) * Rot(0, 90, 0) * Cylinder(SLOT_W / 2, PLATE_T + 2)
    # two slots along Y: screw 1 at (cx-SO, cy+SO), screw 2 at (cx+SO, cy-SO), each free to move +-ADJ
    br -= slot(cx - SO, cy + SO, ARM_TOP - TOP_T / 2, slot_len, False, TOP_T + 2)
    br -= slot(cx + SO, cy - SO, ARM_TOP - TOP_T / 2, slot_len, False, TOP_T + 2)
    return br

# ------------------------------------------------------------------ CARRIER
def build_carrier():
    # upper shelf: front edge flush with the X switch's +X face, margin behind and to the sides
    x_lo, x_hi = sx - SW_L / 2 - PAD, sx + SW_W / 2
    wall_y1 = sy + SW_W / 2 + WIRE_GAP + PAD
    y_lo, y_hi = sy - SW_L / 2 - PAD, max(sy + SW_L / 2 + PAD, wall_y1)
    upper = slab(x_lo, x_hi, y_lo, y_hi, X_Z - TOP_T, X_Z)
    # plate that lies on the arm's clamp pad, with the connecting strip to the shelf
    clamp = slab(cx - SO - ADJ - SLOT_W / 2 - EDGE, cx + SO + ADJ + SLOT_W / 2 + EDGE,
                 cy - SO - SLOT_W / 2 - EDGE, cy + SO + SLOT_W / 2 + EDGE, X_Z - TOP_T, X_Z)
    link = strip((cx, cy), (sx, sy), 7.0, X_Z - TOP_T, X_Z)
    # lower shelf for the Y switch (long side faces -Y), wall behind it with room for the solder pins
    low = slab(sx - SW_L / 2 - PAD, sx + SW_L / 2 + PAD, sy - SW_W / 2, wall_y1, Y_Z - Y_SHELF_T, Y_Z)
    wall_y0 = sy + SW_W / 2 + WIRE_GAP
    wall = Pos((x_lo + x_hi) / 2, (wall_y0 + wall_y1) / 2, ((Y_Z - Y_SHELF_T) + (X_Z - TOP_T / 2)) / 2) * \
        Box(x_hi - x_lo, wall_y1 - wall_y0, (X_Z - TOP_T / 2) - (Y_Z - Y_SHELF_T))
    # Printability: when printed upside down the lower shelf must not hang from one wall. Two side walls (with a
    # small tab of upper plate on the +X side to anchor the right one, well below the X lever) let it bridge.
    side_y0, side_y1 = sy - SW_W / 2, wall_y1
    side_z0, side_z1 = Y_Z - Y_SHELF_T, X_Z - TOP_T / 2
    sides = None
    for k in (-1, 1):
        w = Pos(sx + k * (SW_L / 2 + 2.0), (side_y0 + side_y1) / 2, (side_z0 + side_z1) / 2) * \
            Box(PAD - 1.0, side_y1 - side_y0, side_z1 - side_z0)
        sides = w if sides is None else sides + w
    tab = Pos((sx + SW_W / 2 + sx + SW_L / 2 + PAD) / 2, (side_y0 + side_y1) / 2, X_Z - TOP_T / 2) * \
        Box((sx + SW_L / 2 + PAD) - (sx + SW_W / 2) + 1.0, side_y1 - side_y0, TOP_T)
    car = upper + clamp + link + low + wall + sides + tab
    # slots along X that cross the bridge's slots
    car -= slot(cx - SO, cy + SO, X_Z - TOP_T / 2, slot_len, True, TOP_T + 2)
    car -= slot(cx + SO, cy - SO, X_Z - TOP_T / 2, slot_len, True, TOP_T + 2)
    # X switch pilot holes (along Y); Y switch pilot holes (along X) with access holes above them
    for k in (-1, 1):
        car -= Pos(sx, sy + k * SW_HOLE_SPACING / 2, X_Z - TOP_T / 2) * Cylinder(SW_HOLE / 2, TOP_T + 2)
        xx = sx + k * SW_HOLE_SPACING / 2
        car -= Pos(xx, sy, Y_Z - Y_SHELF_T / 2) * Cylinder(SW_HOLE / 2, Y_SHELF_T + 2)
        car -= Pos(xx, sy, X_Z - TOP_T / 2) * Cylinder(SCREW_HEAD / 2, TOP_T + 2)
    return car

arm, bridge, carrier = build_arm(), build_bridge(), build_carrier()

# ------------------------------------------------------------------ clearance check over the whole sliding range
y_body = Pos(sx, sy, Y_Z + SW_H / 2) * Box(SW_L, SW_W, SW_H)                            # lower switch
y_pins = Pos(sx, sy + SW_W / 2 + PIN_LEN / 2, Y_Z + PIN_Z) * Box(SW_L, PIN_LEN, 1.5)    # its solder pins
def overlap(a, b):
    try:
        return (a & b).volume
    except Exception:
        return 0.0
worst = {"arm/bridge": 0.0, "arm/carrier": 0.0, "bridge/carrier": 0.0}
for dz in (-ADJ_Z, 0, ADJ_Z):
    worst["arm/bridge"] = max(worst["arm/bridge"], overlap(arm, Pos(0, 0, dz) * bridge))
    for dx in (-ADJ, 0, ADJ):
        for dy in (-ADJ, 0, ADJ):
            moved = Pos(dx, dy, dz)
            for item in (carrier, y_body, y_pins):
                worst["arm/carrier"] = max(worst["arm/carrier"], overlap(arm, moved * item))
            if dz == 0:
                for item in (carrier, y_body, y_pins):
                    worst["bridge/carrier"] = max(worst["bridge/carrier"], overlap(bridge, (moved if item is carrier else moved) * item))
# a screwdriver must reach both motor screws from above for every slider position
DRIVER_R = 2.5
for k in (-1, 1):
    shaft = Pos(k * HOLE_SPACING / 2, 0, (BASE_T + 80) / 2) * Cylinder(DRIVER_R, 80 - BASE_T)
    for dz in (-ADJ_Z, 0, ADJ_Z):
        worst["driver"] = max(worst.get("driver", 0.0), overlap(shaft, Pos(0, 0, dz) * bridge))
        for dx in (-ADJ, 0, ADJ):
            for dy in (-ADJ, 0, ADJ):
                worst["driver"] = max(worst["driver"], overlap(shaft, Pos(dx, dy, dz) * carrier))
assert max(worst.values()) < 1e-3, f"parts collide somewhere in the sliding range: {worst}"

if X_DIR < 0:
    arm, bridge, carrier = (mirror(p, Plane.YZ) for p in (arm, bridge, carrier))

d = abs(math.hypot(cx, cy))
for name, p in (("arm", arm), ("bridge", bridge), ("carrier", carrier)):
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"stack nominal ({sx:.1f}, {sy:.1f}), X shelf top {X_Z:g}; slides +-{ADJ:g} mm in X/Y, +-{ADJ_Z:g} mm in Z; "
      f"clamp centre ({cx:.1f}, {cy:.1f}); worst overlap {max(worst.values()):.4f} mm3")
for name, p in (("arm", arm), ("bridge", bridge), ("carrier", carrier)):
    export_step(p, f"limit_switch_{name}.step"); export_stl(p, f"limit_switch_{name}.stl")
export_stl(Compound([arm, bridge, carrier]), "limit_switch_assembly.stl")
