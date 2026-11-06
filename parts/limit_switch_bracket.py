"""Simple limit-switch bracket for the prototype: two flat printed parts (mm).

Frame: origin = midpoint of the two NEMA motor screws (they lie on the X axis at x = +-15.5), Z up from the motor face.
Lever contact points (where the carriage hits the levers):
  X switch lever at X_HIT = (40, 0, 5),    its lever points +X
  Y switch lever at Y_HIT = (50, -30, 10), its lever points -Y
Switches lie flat (screws vertical), their LONG side (the clicking side) towards the lever direction.

  BASE   thin plate that screws to the motor (2 x M3). Its tongue beyond the motor carries the X switch, which simply
         sits on top. The plate is exactly as thick as the switch's resting height, so the lever is at X_HIT.
  YARM   flat plate that lies on the tongue and carries the Y switch. On the +Y side it stops BEHIND_GAP = 2 mm behind
         the switch's back face (structure to clear). Two M3 x 6 screws from below (through the tongue) go into M3
         nuts held in hex pockets on the arm's underside, beside the switch. This is the part to reprint when the Y position
         needs correcting: change Y_HIT and run the script again.

Both print flat, no supports. Switch screws: M2 x 8 (X) and M2 x 10 (Y), self-tapping through the switch into the printed part.

Run:  python limit_switch_bracket.py -> limit_switch_{base,yarm}.step/.stl and limit_switch_assembly.stl
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
BASE_W = 16.0
# --- where the levers get hit (nominal) ---
X_HIT = (40.0, 0.0, 5.0)
Y_HIT = (50.0, -30.0, 10.0)
LEVER_OUT = 2.5            # the lever sticks out this far in front of the switch's clicking face (assumed)
# --- micro switch (1 A 125 V AC type): long side 12.8 with the lever on it, 6.2 deep from the clicking side to the
# back (3 solder pins stick out of the back), 5.8 thick (assumed, measure it); 2 holes dia 2.0, 6.5 apart ---
SW_L, SW_W, SW_H = 12.8, 6.2, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.7              # pilot for an M2 self-tapping screw
PIN_LEN = 3.5
PAD = 3.0
FILLET = 1.0
# --- joint between the two parts: two M3 screws from below into nuts in the arm's underside ---
JOINT_X = (27.0, 37.0)     # x of the two screws, beside the Y switch
# (JOINT_Y, the y of the two screws, is the middle of the Y arm's depth: set below)
NUT_R, NUT_H = 3.6, 2.6    # hex pocket for an M3 nut (5.5 across flats, 2.4 thick): circumradius, depth
BEHIND_GAP = 2.0           # the Y arm ends this far behind the Y switch's back face (+Y side)

# --- switch positions from the lever contact points ---
X_SW = (X_HIT[0] - LEVER_OUT - SW_W / 2, X_HIT[1], X_HIT[2])       # centre of the X switch body
Y_SW = (Y_HIT[0], Y_HIT[1] + LEVER_OUT + SW_W / 2, Y_HIT[2])       # centre of the Y switch body
X_SEAT, Y_SEAT = X_SW[2] - SW_H / 2, Y_SW[2] - SW_H / 2            # where each switch's underside rests
BASE_T = X_SEAT                                                    # the base is as thick as the X switch's resting height
assert BASE_T >= 1.5, "base plate would be thinner than 1.5 mm"
assert Y_SEAT - BASE_T >= NUT_H + 1.2, "Y arm too thin for the nut pockets"

def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return fillet(box(x0, x1, y0, y1, z0, z1).edges().filter_by(Axis.Z), r)

def cyl_z(x, y, z0, z1, d):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, abs(z1 - z0))

# ------------------------------------------------------------------ BASE (screws to the motor, carries the X switch)
x_front = X_SW[0] + SW_W / 2                      # front face of the X switch: the tongue ends here, the lever is free
fx = HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4
tongue_y0 = Y_SW[1] - SW_W / 2 + 0.5               # tongue reaches under the whole Y arm
tongue_y1 = SW_L / 2 + PAD
tongue_x0 = fx - 1.0

def build_base():
    base = slab(-fx, fx, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)
    base += slab(tongue_x0, x_front, tongue_y0, tongue_y1, 0, BASE_T, 1.5)
    # wider part under the Y arm, clear of the X switch's pocket-free zone, so the joint screws have material around them
    base += slab(tongue_x0, JOINT_X[1] + 6.0, tongue_y0, X_SW[1] - SW_L / 2 - 3.0, 0, BASE_T, 1.5)
    for k in (-1, 1):
        base -= cyl_z(k * HOLE_SPACING / 2, 0, -1, BASE_T + 1, MOTOR_SCREW)
    for k in (-1, 1):                              # pilot holes for the X switch, which sits on top of the tongue
        base -= cyl_z(X_SW[0], k * SW_HOLE_SPACING / 2, -1, BASE_T + 1, SW_HOLE)
    for x in JOINT_X:                              # M3 screws from below
        base -= cyl_z(x, JOINT_Y, -1, BASE_T + 1, MOTOR_SCREW)
    return base

# ------------------------------------------------------------------ Y ARM (flat plate on the base, carries the Y switch)
arm_x0 = JOINT_X[0] - 5.5                        # leaves a 1.9 mm wall around the nut pocket
arm_x1 = Y_SW[0] + SW_L / 2 + PAD
arm_y0 = Y_SW[1] - SW_W / 2                       # front edge flush with the switch's clicking face
arm_y1 = Y_SW[1] + SW_W / 2 + BEHIND_GAP          # back edge: 2 mm behind the switch
JOINT_Y = (arm_y0 + arm_y1) / 2                   # the two screws sit in the middle of the arm's depth, beside the switch

def build_yarm():
    arm = slab(arm_x0, arm_x1, arm_y0, arm_y1, BASE_T, Y_SEAT)
    for x in JOINT_X:                              # hex pocket for an M3 nut on the underside, and the screw's passage
        arm -= Pos(x, JOINT_Y, BASE_T - 1) * extrude(RegularPolygon(radius=NUT_R, side_count=6), amount=NUT_H + 1)
        arm -= cyl_z(x, JOINT_Y, BASE_T - 1, Y_SEAT + 1, MOTOR_SCREW)
    for k in (-1, 1):
        arm -= cyl_z(Y_SW[0] + k * SW_HOLE_SPACING / 2, Y_SW[1], BASE_T - 1, Y_SEAT + 1, SW_HOLE)
    return arm

base, yarm = build_base(), build_yarm()

# ------------------------------------------------------------------ checks
sw_x = Pos(*X_SW) * Box(SW_W, SW_L, SW_H)
sw_y = Pos(*Y_SW) * Box(SW_L, SW_W, SW_H)
pins_x = Pos(X_SW[0] - SW_W / 2 - PIN_LEN / 2, X_SW[1], X_SW[2]) * Box(PIN_LEN, SW_L, 1.5)
pins_y = Pos(Y_SW[0], Y_SW[1] + SW_W / 2 + PIN_LEN / 2, Y_SW[2]) * Box(SW_L, PIN_LEN, 1.5)
def ov(a, b):
    try:
        return (a & b).volume
    except Exception:
        return 0.0
checks = {
    "base/yarm": ov(base, yarm), "base/Y switch": ov(base, sw_y), "base/Y pins": ov(base, pins_y),
    "yarm/X switch": ov(yarm, sw_x), "yarm/X pins": ov(yarm, pins_x),
    "base/X switch": ov(base, sw_x), "yarm/Y switch": ov(yarm, sw_y),
}
bad = {k: round(v, 3) for k, v in checks.items() if v > 1e-3}
assert not bad, f"parts collide: {bad}"
assert tongue_y0 <= arm_y0 + 0.6 and arm_y1 <= tongue_y1, "Y arm does not land on the base's tongue"

def audit(name, part, holes):
    """Every hole must have material all the way round it (no hole half outside the part)."""
    for label, x, y, r, z in holes:
        for i in range(16):
            a = 2 * math.pi * i / 16
            p = Vector(x + (r + 0.6) * math.cos(a), y + (r + 0.6) * math.sin(a), z)
            assert part.is_inside(p), f"{name}: hole '{label}' at ({x:.1f}, {y:.1f}) has no material {r + 0.6:.1f} mm around it"

z_b, z_a = BASE_T / 2, (BASE_T + Y_SEAT) / 2
audit("base", base, [("motor screw", k * HOLE_SPACING / 2, 0, MOTOR_SCREW / 2, z_b) for k in (-1, 1)]
      + [("X switch pilot", X_SW[0], k * SW_HOLE_SPACING / 2, SW_HOLE / 2, z_b) for k in (-1, 1)]
      + [("joint screw", x, JOINT_Y, MOTOR_SCREW / 2, z_b) for x in JOINT_X])
audit("yarm", yarm, [("nut pocket", x, JOINT_Y, NUT_R * math.cos(math.pi / 6), z_a) for x in JOINT_X]
      + [("Y switch pilot", Y_SW[0] + k * SW_HOLE_SPACING / 2, Y_SW[1], SW_HOLE / 2, z_a) for k in (-1, 1)])

parts = (("base", base), ("yarm", yarm))
for name, p in parts:
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm (z {bb.min.Z:.1f} to {bb.max.Z:.1f}), "
          f"{p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"X switch centre {tuple(round(v, 1) for v in X_SW)} (seat {X_SEAT:.1f}), Y switch centre {tuple(round(v, 1) for v in Y_SW)} "
      f"(seat {Y_SEAT:.1f}, base {BASE_T:.1f} mm, arm {Y_SEAT - BASE_T:.1f} mm thick, ends {BEHIND_GAP:g} mm behind the switch); no collisions")
for name, p in parts:
    export_step(p, f"limit_switch_{name}.step")
    export_stl(p, f"limit_switch_{name}.stl", tolerance=0.02, angular_tolerance=0.3)
export_stl(Compound([p for _, p in parts]), "limit_switch_assembly.stl", tolerance=0.02, angular_tolerance=0.3)

import json
json.dump({"X_HIT": X_HIT, "Y_HIT": Y_HIT, "X_SW": X_SW, "Y_SW": Y_SW, "LEVER_OUT": LEVER_OUT, "SW_L": SW_L, "SW_W": SW_W,
           "SW_H": SW_H, "SW_HOLE_SPACING": SW_HOLE_SPACING, "HOLE_SPACING": HOLE_SPACING, "BASE_T": BASE_T,
           "X_SEAT": X_SEAT, "Y_SEAT": Y_SEAT, "BEHIND_GAP": BEHIND_GAP}, open("viewer_params.json", "w"))
