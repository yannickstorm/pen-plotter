"""Simple limit-switch bracket for the prototype: two flat printed parts (mm).

Frame: origin = midpoint of the two NEMA motor screws (they lie on the X axis at x = +-15.5), Z up from the motor face.
Lever contact points (where the carriage hits the levers):
  X switch lever at X_HIT = (40, 0, 5),    its lever points +X
  Y switch lever at Y_HIT = (50, -30, 10), its lever points -Y
Switches lie flat (screws vertical), their LONG side (the clicking side) towards the lever direction.

  BASE   plate that screws to the motor (2 x M3) and carries the X switch in a pocket in a tongue beyond the motor.
         The tongue also has two nut traps (underside) where the Y arm is screwed on.
  YARM   thin flat plate that lies on the base's tongue (2 x M3 x 8 into the nut traps) and carries the Y switch.
         This is the part to reprint when the Y position needs correcting: change Y_HIT and run the script again.

Both print flat, no supports. Switch screws: M2 x 8 self-tapping (through the switch into the printed part).

Run:  python limit_switch_bracket.py -> limit_switch_{base,yarm}.step/.stl and limit_switch_assembly.stl
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
# --- micro switch (1 A 125 V AC type): long side 12.8 with the lever on it, 6.2 deep from the clicking side to the
# back (3 solder pins stick out of the back), 5.8 thick (assumed, measure it); 2 holes dia 2.0, 6.5 apart ---
SW_L, SW_W, SW_H = 12.8, 6.2, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.7              # pilot for an M2 self-tapping screw
PIN_LEN = 3.5
POCKET_CL = 0.3            # clearance around the X switch in its pocket
PAD = 3.0
FILLET = 1.0
# --- joint between the two parts: two M3 screws into nut traps in the base's underside ---
JOINT_X = (26.0, 34.0)     # x of the two screws
JOINT_Y = -14.0
NUT_R, NUT_H = 3.6, 2.6    # hex nut trap for an M3 nut (5.5 across flats): circumradius, depth

# --- switch positions from the lever contact points ---
X_SW = (X_HIT[0] - LEVER_OUT - SW_W / 2, X_HIT[1], X_HIT[2])       # centre of the X switch body
Y_SW = (Y_HIT[0], Y_HIT[1] + LEVER_OUT + SW_W / 2, Y_HIT[2])       # centre of the Y switch body
X_SEAT, Y_SEAT = X_SW[2] - SW_H / 2, Y_SW[2] - SW_H / 2            # where each switch's underside rests
assert Y_SEAT - BASE_T >= 2.0, "Y arm would be thinner than 2 mm"
assert X_SEAT >= 1.5, "X switch pocket floor would be thinner than 1.5 mm"

def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)

def slab(x0, x1, y0, y1, z0, z1, r=FILLET):
    return fillet(box(x0, x1, y0, y1, z0, z1).edges().filter_by(Axis.Z), r)

def cyl_z(x, y, z0, z1, d):
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(d / 2, abs(z1 - z0))

# ------------------------------------------------------------------ BASE (screws to the motor, carries the X switch)
x_front = X_SW[0] + SW_W / 2                      # front face of the X switch: the tongue ends here, the lever is free
fx = HOLE_SPACING / 2 + MOTOR_SCREW / 2 + 4
tongue_y0 = JOINT_Y - 4.0                         # tongue reaches over to the screws of the Y arm
tongue_y1 = SW_L / 2 + PAD
tongue_x0 = fx - 1.0

def build_base():
    base = slab(-fx, fx, -BASE_W / 2, BASE_W / 2, 0, BASE_T, 1.5)
    base += slab(tongue_x0, x_front, tongue_y0, tongue_y1, 0, BASE_T, 1.5)
    for k in (-1, 1):
        base -= cyl_z(k * HOLE_SPACING / 2, 0, -1, BASE_T + 1, MOTOR_SCREW)
    # pocket for the X switch, open towards its lever (+X); the floor is where the switch rests
    base -= box(X_SW[0] - SW_W / 2 - POCKET_CL, x_front + 1, -SW_L / 2 - POCKET_CL, SW_L / 2 + POCKET_CL, X_SEAT, BASE_T + 1)
    for k in (-1, 1):
        base -= cyl_z(X_SW[0], k * SW_HOLE_SPACING / 2, -1, X_SEAT + 1, SW_HOLE)
    # joint with the Y arm: M3 through-holes with a nut trap on the underside
    for x in JOINT_X:
        base -= cyl_z(x, JOINT_Y, -1, BASE_T + 1, MOTOR_SCREW)
        nut = extrude(RegularPolygon(radius=NUT_R, side_count=6), amount=NUT_H + 1)
        base -= Pos(x, JOINT_Y, -1) * nut
    return base

# ------------------------------------------------------------------ Y ARM (flat plate on the base, carries the Y switch)
arm_x0 = JOINT_X[0] - 4.0
arm_x1 = Y_SW[0] + SW_L / 2 + PAD
arm_y0 = Y_SW[1] - SW_W / 2                       # front edge flush with the switch's clicking face
arm_y1 = JOINT_Y + 4.0

def build_yarm():
    arm = slab(arm_x0, arm_x1, arm_y0, arm_y1, BASE_T, Y_SEAT)
    for x in JOINT_X:
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
assert arm_y1 <= tongue_y1 and arm_y1 >= tongue_y0 + 1.0, "Y arm does not land on the base's tongue"

parts = (("base", base), ("yarm", yarm))
for name, p in parts:
    bb = p.bounding_box()
    print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm (z {bb.min.Z:.1f} to {bb.max.Z:.1f}), "
          f"{p.volume:.0f} mm3, valid={p.is_valid}, solids={len(p.solids())}")
print(f"X switch centre {tuple(round(v, 1) for v in X_SW)} (seat {X_SEAT:.1f}), Y switch centre {tuple(round(v, 1) for v in Y_SW)} "
      f"(seat {Y_SEAT:.1f}, arm {Y_SEAT - BASE_T:.1f} mm thick); no collisions")
for name, p in parts:
    export_step(p, f"limit_switch_{name}.step")
    export_stl(p, f"limit_switch_{name}.stl", tolerance=0.02, angular_tolerance=0.3)
export_stl(Compound([p for _, p in parts]), "limit_switch_assembly.stl", tolerance=0.02, angular_tolerance=0.3)

import json
json.dump({"X_HIT": X_HIT, "Y_HIT": Y_HIT, "X_SW": X_SW, "Y_SW": Y_SW, "LEVER_OUT": LEVER_OUT, "SW_L": SW_L, "SW_W": SW_W,
           "SW_H": SW_H, "SW_HOLE_SPACING": SW_HOLE_SPACING, "HOLE_SPACING": HOLE_SPACING, "BASE_T": BASE_T,
           "X_SEAT": X_SEAT, "Y_SEAT": Y_SEAT}, open("viewer_params.json", "w"))
