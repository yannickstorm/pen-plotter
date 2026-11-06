"""Limit-switch bracket for the prototype: ONE flat printed part (mm).

Frame: origin = midpoint of the two NEMA motor screws (they lie on the X axis at x = +-15.5), Z up from the motor face.
Lever contact points (where the carriage hits the levers):
  X switch lever at X_HIT = (40, 0, 5),    its lever points +X
  Y switch lever at Y_HIT = (35, -30, 10), its lever points -Y
Switches lie flat (screws vertical), their LONG side (the clicking side) towards the lever direction.

The part is a thin plate that screws to the motor (2 x M3). Its tongue beyond the motor carries the X switch, which simply
sits on it (the plate is as thick as the switch's resting height). A raised platform on the tongue carries the Y switch;
it stops BEHIND_GAP = 2 mm behind the switch's back face on the +Y side (structure to clear). No part of it reaches
beyond the farthest lever contact point in X (X_LIMIT), so the Y switch may hang slightly over the platform's edge.
To correct a position, change X_HIT / Y_HIT and run the script again, then reprint (about 25 minutes).

Switch screws: self-tapping M2 x 8 (X) and M2 x 10 (Y) through the switch into the printed part.
Prints flat, underside on the bed, no supports.

Run:  python limit_switch_bracket.py -> limit_switch_part.step/.stl
"""
import math
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
BASE_W = 16.0
# --- where the levers get hit (nominal) ---
X_HIT = (40.0, 0.0, 5.0)
Y_HIT = (35.0, -30.0, 10.0)
LEVER_OUT = 2.5            # the lever sticks out this far in front of the switch's clicking face (assumed)
# --- micro switch (1 A 125 V AC type): long side 12.8 with the lever on it, 6.2 deep from the clicking side to the
# back (3 solder pins stick out of the back), 5.8 thick (assumed, measure it); 2 holes dia 2.0, 6.5 apart ---
SW_L, SW_W, SW_H = 12.8, 6.2, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.7              # pilot for an M2 self-tapping screw
SW_HOLE_DEPTH = 6.0        # blind pilot depth on the Y platform
PIN_LEN = 3.5
BEHIND_GAP = 2.0           # the Y platform ends this far behind the Y switch's back face (+Y side)
PAD = 3.0
FILLET = 1.0

# --- switch positions from the lever contact points ---
X_SW = (X_HIT[0] - LEVER_OUT - SW_W / 2, X_HIT[1], X_HIT[2])       # centre of the X switch body
Y_SW = (Y_HIT[0], Y_HIT[1] + LEVER_OUT + SW_W / 2, Y_HIT[2])       # centre of the Y switch body
X_SEAT, Y_SEAT = X_SW[2] - SW_H / 2, Y_SW[2] - SW_H / 2            # where each switch's underside rests
BASE_T = X_SEAT                                                    # the plate is as thick as the X switch's resting height
assert BASE_T >= 1.5, "plate would be thinner than 1.5 mm"
assert Y_SEAT > BASE_T, "Y platform would not rise above the plate"

def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return fillet(box(x0, x1, y0, y1, z0, z1).edges().filter_by(Axis.Z), r)

def cyl_z(x, y, z0, z1, d):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, abs(z1 - z0))

# ------------------------------------------------------------------ the part
x_front = X_SW[0] + SW_W / 2                      # front face of the X switch: the tongue ends here, the lever is free
fx = HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4
tongue_x0 = fx - 1.0
X_LIMIT = max(X_HIT[0], Y_HIT[0])                 # nothing may reach beyond the farthest lever contact point in X
plat_x0, plat_x1 = Y_SW[0] - SW_L / 2 - PAD, min(Y_SW[0] + SW_L / 2 + PAD, X_LIMIT)
plat_y0 = Y_SW[1] - SW_W / 2                      # front edge flush with the switch's clicking face
plat_y1 = Y_SW[1] + SW_W / 2 + BEHIND_GAP         # back edge: 2 mm behind the switch
tongue_y0 = plat_y0 - 0.5                         # the plate reaches under the whole platform
tongue_y1 = SW_L / 2 + PAD

def build():
    p = slab(-fx, fx, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)                      # motor plate
    p += slab(tongue_x0, x_front, tongue_y0, tongue_y1, 0, BASE_T, 1.5)             # tongue under the X switch
    p += slab(tongue_x0, plat_x1, tongue_y0, X_SW[1] - SW_L / 2 - 3.0, 0, BASE_T, 1.5)   # foot under the Y platform
    p += slab(plat_x0, plat_x1, plat_y0, plat_y1, 0, Y_SEAT, 1.0)                   # raised platform for the Y switch
    for k in (-1, 1):
        p -= cyl_z(k * HOLE_SPACING / 2, 0, -1, BASE_T + 1, MOTOR_SCREW)            # motor screws
        p -= cyl_z(X_SW[0], k * SW_HOLE_SPACING / 2, -1, BASE_T + 1, SW_HOLE)        # X switch pilot holes
        p -= cyl_z(Y_SW[0] + k * SW_HOLE_SPACING / 2, Y_SW[1], Y_SEAT - SW_HOLE_DEPTH, Y_SEAT + 1, SW_HOLE)   # Y switch pilots
    return p

part = build()

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
checks = {"X switch": ov(part, sw_x), "Y switch": ov(part, sw_y), "X pins": ov(part, pins_x), "Y pins": ov(part, pins_y)}
bad = {k: round(v, 3) for k, v in checks.items() if v > 1e-3}
assert not bad, f"the part collides with a switch: {bad}"

def audit(holes):
    """Every hole must have material all the way round it (no hole half outside the part)."""
    for label, x, y, r, z in holes:
        for i in range(16):
            a = 2 * math.pi * i / 16
            pt = Vector(x + (r + 0.6) * math.cos(a), y + (r + 0.6) * math.sin(a), z)
            assert part.is_inside(pt), f"hole '{label}' at ({x:.1f}, {y:.1f}) has no material {r + 0.6:.1f} mm around it"
audit([("motor screw", k * HOLE_SPACING / 2, 0, MOTOR_SCREW / 2, BASE_T / 2) for k in (-1, 1)]
      + [("X switch pilot", X_SW[0], k * SW_HOLE_SPACING / 2, SW_HOLE / 2, BASE_T / 2) for k in (-1, 1)]
      + [("Y switch pilot", Y_SW[0] + k * SW_HOLE_SPACING / 2, Y_SW[1], SW_HOLE / 2, Y_SEAT - 1) for k in (-1, 1)])
assert len(part.solids()) == 1 and part.is_valid
assert part.bounding_box().max.X <= X_LIMIT + 1e-6, "the part reaches beyond the lever contact points in X"

bb = part.bounding_box()
print(f"part: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm (z {bb.min.Z:.1f} to {bb.max.Z:.1f}), "
      f"{part.volume:.0f} mm3, valid={part.is_valid}, solids={len(part.solids())}")
print(f"X switch centre {tuple(round(v, 1) for v in X_SW)} (rests at {X_SEAT:.1f}), "
      f"Y switch centre {tuple(round(v, 1) for v in Y_SW)} (rests at {Y_SEAT:.1f}); platform ends {BEHIND_GAP:g} mm behind it; no collisions")
export_step(part, "limit_switch_part.step")
export_stl(part, "limit_switch_part.stl", tolerance=0.02, angular_tolerance=0.3)
export_stl(part, "limit_switch_assembly.stl", tolerance=0.02, angular_tolerance=0.3)

import json
json.dump({"X_HIT": X_HIT, "Y_HIT": Y_HIT, "X_SW": X_SW, "Y_SW": Y_SW, "LEVER_OUT": LEVER_OUT, "SW_L": SW_L, "SW_W": SW_W,
           "SW_H": SW_H, "SW_HOLE_SPACING": SW_HOLE_SPACING, "HOLE_SPACING": HOLE_SPACING, "BASE_T": BASE_T,
           "X_SEAT": X_SEAT, "Y_SEAT": Y_SEAT, "BEHIND_GAP": BEHIND_GAP}, open("viewer_params.json", "w"))
