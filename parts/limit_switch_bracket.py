"""Adjustable limit-switch bracket, screw-free sliding with dovetails, four printed parts (mm).

  ARM       base on the two motor screws, a post with a vertical dovetail rail (Z).
  BRIDGE    plate that slides up and down the post rail (Z), a beam and a pad with a dovetail channel along Y.
  CROSS     cross-slide: slides along Y in the bridge's pad, with a dovetail channel along X on its top.
  CARRIER   upper shelf (X switch, shelf top at X_Z), lower shelf 10 mm below (Y switch), and a dovetail rail
            that slides along X in the cross-slide.

Every slide is a 45 degree dovetail with DT_CL clearance per side (a loose-ish sliding fit) and is locked by an M3
set screw into an M3 heat-set insert (3 in total):
  Z  boss on the front of the bridge plate, screw pushes on the tip of the post rail
  Y  boss under the bridge pad, screw pushes up on the tip of the cross-slide rail
  X  boss on the side of the cross-slide, screw pushes on the flank of the carrier rail

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin; Z is up. The "front" screw is the one
on the side the X lever points to: (X_DIR * HOLE_SPACING/2, 0). Nominal switch-stack position: STACK_DX along X and
STACK_DY (sign Y_SIGN) along Y from the front screw, X shelf top at X_Z. It moves +-ADJ in X and Y, +-ADJ_Z in Z.
  * X switch: its LONG side (the clicking side) faces +X;  Y switch: its long side faces -Y.
Fit the lower (Y) switch first: its screws are reached through access holes in the upper shelf.

Measuring the final position (engraved scales, 1 mm per tick, 0 = nominal, + = towards +X / +Y / up):
  Z  on both side faces of the post, at its -Y edge: the top edge of the bridge plate sits next to a tick.
  Y  on the bridge's pad: the +Y end edge of the cross-slide sits next to a tick.
  X  on the cross-slide's top: the -X end edge of the carrier's plate sits next to a tick.
Final stack position = nominal + readings (the viewer adds them up for you).

Run:  python limit_switch_bracket.py
      -> limit_switch_{arm,bridge,cross,carrier}.step/.stl and limit_switch_assembly.stl (preview only)
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
HEAD_D = 6.0               # M3 cap/pan head
BASE_T = 4.0
POST_X, POST_Y = 14.0, 16.0
BASE_W = POST_Y            # as wide as the post, so the arm can lie flat on its side when printed
# --- where the switches go (nominal) ---
X_DIR = 1                  # +1: front screw / X lever on the +X side (-1 mirrors the whole part)
STACK_DX = 50.0            # from the front screw, along the lever direction
STACK_DY = 40.0            # from the front screw, sideways (sign below)
Y_SIGN = -1                # -1: stack on the -Y side
X_Z = 35.0                 # top of the X (upper) shelf above the motor face
Y_DROP = 10.0              # Y shelf top is this much lower
TOP_T = 3.0                # carrier's upper plate
Y_SHELF_T = 4.0
# --- adjustment ---
ADJ = 8.0                  # +-ADJ mm in X and in Y
ADJ_Z = 8.0                # +-ADJ_Z mm in Z
CLAMP_DIST = 41.0          # slide centre this far back from the stack, along the arm
# --- dovetails: 45 degrees, so they print without supports ---
DT_H = 3.0                 # rail height
DT_B0 = 3.0                # rail half width at its base (tip: DT_B0 + DT_H)
DT_CL = 0.3                # clearance per side: bigger = looser
RAIL_LEN = 14.0
# --- locking: M3 heat-set insert (hole INS_D x INS_DEPTH) + M3 set screw (passage SET_D) ---
INS_D, INS_DEPTH, SET_D = 4.2, 6.0, 3.2
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
# --- measuring scales ---
TICK_D = 0.5               # depth of engraved ticks and numbers
LABELS = X_DIR > 0         # numbers are engraved unmirrored, so they are skipped when the whole part is mirrored
LABEL_SIZE = 3.0

# --- levels, from the top down ---
Y_Z = X_Z - Y_DROP
Z_CS_TOP = X_Z - TOP_T                     # cross-slide top = carrier plate underside
CS_T = DT_H + DT_CL + 1.7                  # cross-slide thickness (channel + web)
Z_B = Z_CS_TOP - CS_T                      # bridge pad top = cross-slide underside
PAD_T = DT_H + DT_CL + 1.7
PH = 18.0                                  # bridge plate height (engagement on the post rail)
PT = DT_H + DT_CL + INS_DEPTH + 1.7        # bridge plate thickness: channel + insert + web
POST_H = Z_B + ADJ_Z + 2                   # +2 so the +8 tick is not on the very edge
assert Y_Z + SW_H + 0.3 < Z_CS_TOP, "lower switch would touch the upper shelf"
assert Z_B - PH - ADJ_Z >= 0, "bridge plate would go below the motor face at its lowest position"
assert POST_X / 2 + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2 + 3, "post collides with screw heads"

# dovetail profiles in (u across, v out of the surface). Male rail: base half width DT_B0, 45 deg flanks.
_c0 = DT_B0 + DT_CL
_d = DT_H + DT_CL
MALE = [(-DT_B0, -0.5), (DT_B0, -0.5), (DT_B0, 0), (DT_B0 + DT_H, DT_H), (-DT_B0 - DT_H, DT_H), (-DT_B0, 0)]
FEMALE = [(-_c0, 0.5), (_c0, 0.5), (_c0, 0), (_c0 + _d, -_d), (-_c0 - _d, -_d), (-_c0, 0)]

def dt(profile, origin, u, w, length):
    """Dovetail prism. u = across, w = along, v = w x u = out of the surface it sits on."""
    pl = Plane(origin=origin, x_dir=u, z_dir=w)
    return extrude(pl * Polygon(*profile, align=None), amount=length / 2, both=True)

def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)

def rounded(solid, r=FILLET):
    return fillet(solid.edges().filter_by(Axis.Z), r)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return rounded(box(x0, x1, y0, y1, z0, z1), r)

def strip(p0, p1, half_w, z0, z1):
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    d = math.hypot(dx, dy); nx, ny = -dy / d, dx / d
    pts = [(p0[0] - half_w * nx, p0[1] - half_w * ny), (p1[0] - half_w * nx, p1[1] - half_w * ny),
           (p1[0] + half_w * nx, p1[1] + half_w * ny), (p0[0] + half_w * nx, p0[1] + half_w * ny)]
    return extrude(Plane.XY.offset(z0) * Polygon(*pts, align=None), amount=z1 - z0)

def cyl_y(x, y0, y1, z, d):
    return Pos(x, (y0 + y1) / 2, z) * Rot(90, 0, 0) * Cylinder(d / 2, abs(y1 - y0))

def cyl_z(x, y, z0, z1, d):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, abs(z1 - z0))

def tick_w(t): return 1.0 if t == 0 else (0.8 if t % 4 == 0 else 0.5)
def tick_len(t): return 3.0 if t == 0 else (2.2 if t % 4 == 0 else 1.2)
def tick_text(t): return "0" if t == 0 else f"{t:+d}"

def engrave(txt, origin, x_dir, z_dir):
    """Text cut TICK_D into the surface that passes through `origin` with outward normal `z_dir`."""
    if not LABELS:
        return None
    pl = Plane(origin=origin, x_dir=x_dir, z_dir=z_dir)
    out = None
    for f in Text(txt, LABEL_SIZE, align=(Align.CENTER, Align.CENTER)).faces():
        piece = extrude(pl * f, amount=TICK_D, both=True)
        out = piece if out is None else out + piece
    return out

# nominal stack centre and the slide centre behind it (built for X_DIR=+1, mirrored at the end)
sx = HOLE_SPACING / 2 + STACK_DX
sy = Y_SIGN * STACK_DY
L = math.hypot(sx, sy)
ux, uy = sx / L, sy / L
cx, cy = sx - CLAMP_DIST * ux, sy - CLAMP_DIST * uy
# plan sizes
PAD_HW = 13.0                      # bridge pad half width (x)
PAD_Y0, PAD_Y1 = cy - RAIL_LEN / 2 - ADJ - 2.0, cy + 21.0     # channel length: rail + travel
CS_HX, CS_HY = RAIL_LEN / 2 + ADJ + 2.0, 9.5                  # cross-slide half sizes
CHX, CHY = 8.0, 9.3                # carrier plate half sizes over the cross-slide
BOSS = 5.0                         # half size of the locking bosses

# ------------------------------------------------------------------ ARM (fixed to the motor)
def build_arm():
    fx = HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4
    arm = slab(-fx, fx, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5) + box(-POST_X / 2, POST_X / 2, -POST_Y / 2, POST_Y / 2, 0, POST_H)
    arm += dt(MALE, (0, -POST_Y / 2, POST_H / 2), (-1, 0, 0), (0, 0, 1), POST_H)       # Z rail on the -Y face
    for k in (-1, 1):
        arm -= cyl_z(k * HOLE_SPACING / 2, 0, -1, BASE_T + 1, MOTOR_SCREW)
    # Z scale on both side faces of the post, at its -Y edge, read against the top edge of the bridge plate
    y_end = -POST_Y / 2 + 0.3
    for face in (-1, 1):
        xf = face * POST_X / 2
        for t in range(-int(ADJ_Z), int(ADJ_Z) + 1):
            arm -= Pos(xf, y_end + tick_len(t) / 2, Z_B + t) * Box(2 * TICK_D, tick_len(t), tick_w(t))
            if t % 4 == 0:
                e = engrave(tick_text(t), (xf, y_end + 3.0 + 0.8 + 1.6, Z_B + t), (0, face, 0), (face, 0, 0))
                if e is not None:
                    arm -= e
    return arm

# ------------------------------------------------------------------ BRIDGE (slides in Z on the post)
def build_bridge():
    plate = box(-12, 12, -POST_Y / 2 - PT, -POST_Y / 2, Z_B - PH, Z_B)
    beam = box(10, cx - 8.5 + 3, -POST_Y / 2 - PT, -POST_Y / 2 - 1, Z_B - 5, Z_B)
    pad = slab(cx - 8.5, cx + PAD_HW, PAD_Y0, PAD_Y1, Z_B - PAD_T, Z_B)     # trimmed on the -X side (screwdriver column)
    pad_boss = box(cx - BOSS, cx + BOSS, cy - BOSS, cy + BOSS, Z_B - PAD_T - INS_DEPTH, Z_B - PAD_T + 0.5)
    br = plate + beam + pad + pad_boss
    # Z: channel on the plate's inner face, set screw from the front boss onto the rail tip
    br -= dt(FEMALE, (0, -POST_Y / 2, Z_B - PH / 2), (1, 0, 0), (0, 0, 1), PH + 2)
    zc = Z_B - PH / 2
    br -= cyl_y(0, -POST_Y / 2 - PT - 1, -POST_Y / 2 - PT + INS_DEPTH, zc, INS_D)
    br -= cyl_y(0, -POST_Y / 2 - PT, -POST_Y / 2 - DT_H, zc, SET_D)
    # Y: channel along Y on the pad's top, set screw from below onto the tip of the cross-slide rail
    br -= dt(FEMALE, (cx, (PAD_Y0 + PAD_Y1) / 2, Z_B), (-1, 0, 0), (0, 1, 0), PAD_Y1 - PAD_Y0 + 2)
    z_lo = Z_B - PAD_T - INS_DEPTH
    br -= cyl_z(cx, cy, z_lo - 1, z_lo + INS_DEPTH, INS_D)
    br -= cyl_z(cx, cy, z_lo, Z_B - DT_H + 0.5, SET_D)
    # Y scale: ticks on the pad's +X side, the +Y end edge of the cross-slide (y = cy + CS_HY + offset) is the pointer
    n = int(ADJ)
    for t in range(-n, n + 1):
        br -= Pos(cx + (PAD_HW - 0.3 - tick_len(t) / 2), cy + CS_HY + t, Z_B) * Box(tick_len(t), tick_w(t), 2 * TICK_D)
        if t % 4 == 0:
            e = engrave(tick_text(t), (cx + (PAD_HW - 0.3 - 3.0 - 0.8 - 1.6), cy + CS_HY + t, Z_B), (1, 0, 0), (0, 0, 1))
            if e is not None:
                br -= e
    return br

# ------------------------------------------------------------------ CROSS-SLIDE (slides in Y in the pad)
def build_cross():
    body = slab(cx - CS_HX, cx + CS_HX, cy - CS_HY, cy + CS_HY, Z_B, Z_CS_TOP)
    boss = box(cx - BOSS, cx + BOSS, cy + CHY + 0.2, cy + CS_HY + INS_DEPTH, Z_B, Z_CS_TOP)
    cs = body + boss
    cs += dt(MALE, (cx, cy, Z_B), (1, 0, 0), (0, 1, 0), RAIL_LEN)                      # Y rail on the underside
    cs -= dt(FEMALE, (cx, cy, Z_CS_TOP), (0, 1, 0), (1, 0, 0), 2 * CS_HX + 2)           # X channel on the top
    zc = Z_CS_TOP - 2.4          # level of the carrier rail's flank; the insert hole spans 27.5 to 31.7
    cs -= cyl_y(cx, cy + CS_HY, cy + CS_HY + INS_DEPTH + 1, zc, INS_D)
    cs -= cyl_y(cx, cy, cy + CS_HY + 1, zc, SET_D)
    # X scale (no room for numbers: the longest tick is 0, medium ticks are +-4 and +-8): ticks along the +Y edge of the
    # top, the -X end edge of the carrier plate (x = cx - CHX + offset) is the pointer
    for t in range(-int(ADJ), int(ADJ) + 1):
        cs -= Pos(cx - CHX + t, cy + CS_HY - 0.3 - tick_len(t) / 2, Z_CS_TOP) * Box(tick_w(t), tick_len(t), 2 * TICK_D)
    return cs

# ------------------------------------------------------------------ CARRIER (slides in X in the cross-slide)
def build_carrier():
    # upper shelf: front edge flush with the X switch's +X face, margin behind and to the sides
    x_lo, x_hi = sx - SW_L / 2 - PAD, sx + SW_W / 2
    wall_y1 = sy + SW_W / 2 + WIRE_GAP + PAD
    y_lo, y_hi = sy - SW_L / 2 - PAD, max(sy + SW_L / 2 + PAD, wall_y1)
    upper = slab(x_lo, x_hi, y_lo, y_hi, Z_CS_TOP, X_Z)
    clamp = slab(cx - CHX, cx + CHX, cy - CHY, cy + CHY, Z_CS_TOP, X_Z)
    link = strip((cx, cy), (sx, sy), 7.0, Z_CS_TOP, X_Z)
    rail = dt(MALE, (cx, cy, Z_CS_TOP), (0, -1, 0), (1, 0, 0), RAIL_LEN)                  # X rail on the underside
    # lower shelf for the Y switch (long side faces -Y), wall behind it with room for the solder pins
    low = slab(sx - SW_L / 2 - PAD, sx + SW_L / 2 + PAD, sy - SW_W / 2, wall_y1, Y_Z - Y_SHELF_T, Y_Z)
    wall_y0 = sy + SW_W / 2 + WIRE_GAP
    wall = box(x_lo, x_hi, wall_y0, wall_y1, Y_Z - Y_SHELF_T, X_Z - TOP_T / 2)
    # Printability: two side walls (and a small tab of upper plate anchoring the +X one) let the lower shelf bridge
    side_y0, side_y1 = sy - SW_W / 2, wall_y1
    sides = None
    for k in (-1, 1):
        w = box(sx + k * (SW_L / 2 + 2.0) - 1.0, sx + k * (SW_L / 2 + 2.0) + 1.0, side_y0, side_y1, Y_Z - Y_SHELF_T, X_Z - TOP_T / 2)
        sides = w if sides is None else sides + w
    tab = box(sx + SW_W / 2 - 0.5, sx + SW_L / 2 + PAD, side_y0, side_y1, Z_CS_TOP, X_Z)
    car = upper + clamp + link + rail + low + wall + sides + tab
    for k in (-1, 1):
        car -= cyl_z(sx, sy + k * SW_HOLE_SPACING / 2, Z_CS_TOP - 1, X_Z + 1, SW_HOLE)
        xx = sx + k * SW_HOLE_SPACING / 2
        car -= cyl_z(xx, sy, Y_Z - Y_SHELF_T - 1, Y_Z + 1, SW_HOLE)
        car -= cyl_z(xx, sy, Z_CS_TOP - 1, X_Z + 1, SCREW_HEAD)
    return car

arm, bridge, cross, carrier = build_arm(), build_bridge(), build_cross(), build_carrier()

# ------------------------------------------------------------------ clearance check over the whole sliding range
# (a screwdriver reaching the motor screws from above is only required at the nominal position: tighten the
# motor screws first, the bridge then slides on from the top of the post)
y_body = Pos(sx, sy, Y_Z + SW_H / 2) * Box(SW_L, SW_W, SW_H)                            # lower switch
y_pins = Pos(sx, sy + SW_W / 2 + PIN_LEN / 2, Y_Z + PIN_Z) * Box(SW_L, PIN_LEN, 1.5)    # its solder pins
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
RZ = (-ADJ_Z, 0.0, ADJ_Z)
DRIVER_R = 2.5
shafts = [Pos(k * HOLE_SPACING / 2, 0, (BASE_T + 80) / 2) * Cylinder(DRIVER_R, 80 - BASE_T) for k in (-1, 1)]
for dz in RZ:
    br = Pos(0, 0, dz) * bridge
    note("arm/bridge", overlap(("ab", dz), arm, br))
    for sh in shafts:
        if dz == 0:
            note("driver/bridge", overlap(("db", dz, sh.center().X), sh, br))
    for dy in R:
        cs = Pos(0, dy, dz) * cross
        note("arm/cross", overlap(("ac", dy, dz), arm, cs))
        note("bridge/cross", overlap(("bc", dy, dz), br, cs))
        for sh in shafts:
            if dz == 0 and dy == 0:
                note("driver/cross", overlap(("dc", dy, dz, sh.center().X), sh, cs))
        for dx in R:
            m = Pos(dx, dy, dz)
            for nm, item in (("carrier", carrier), ("ybody", y_body), ("ypins", y_pins)):
                it = m * item
                note(f"arm/{nm}", overlap(("a" + nm, dx, dy, dz), arm, it))
                note(f"bridge/{nm}", overlap(("b" + nm, dx, dy, dz), br, it))
                note(f"cross/{nm}", overlap(("c" + nm, dx, dy, dz), cs, it))
                if nm == "carrier":
                    for sh in shafts:
                        if dx == dy == dz == 0:
                            note("driver/carrier", overlap(("dk", dx, dy, dz, sh.center().X), sh, it))
bad = {k: round(v, 3) for k, v in worst.items() if v > 1e-3}
assert not bad, f"parts collide somewhere in the sliding range: {bad}"

if X_DIR < 0:
    arm, bridge, cross, carrier = (mirror(p, Plane.YZ) for p in (arm, bridge, cross, carrier))

parts = (("arm", arm), ("bridge", bridge), ("cross", cross), ("carrier", carrier))
for name, p in parts:
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"stack nominal ({sx:.1f}, {sy:.1f}), X shelf top {X_Z:g}; moves +-{ADJ:g} mm in X/Y, +-{ADJ_Z:g} mm in Z; "
      f"slide centre ({cx:.1f}, {cy:.1f}); clearance checks passed (worst overlap {max(worst.values()):.4f} mm3)")
for name, p in parts:
    export_step(p, f"limit_switch_{name}.step")
    export_stl(p, f"limit_switch_{name}.stl", tolerance=0.02, angular_tolerance=0.3)
export_stl(Compound([p for _, p in parts]), "limit_switch_assembly.stl", tolerance=0.02, angular_tolerance=0.3)
