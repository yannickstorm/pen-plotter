"""Limit-switch bracket for the X and Y endstops (all dimensions in mm).

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin.
Z is up. The base sits on the horizontal motor face; the switches sit on a
horizontal shelf SWITCH_Z above it.
  * X switch: lever points +X (along the line of the two motor holes)
  * Y switch: lever points -Y (rotated -90 deg from X)
Flip X_DIR to -1 if the X switch should point the other way.

Run:  python limit_switch_bracket.py   ->  limit_switch_bracket.step / .stl
"""
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
HEAD_D = 6.0               # M3 cap/pan head, keep post clear of it
BASE_T = 4.0               # base plate thickness
BASE_W = 12.0
# --- geometry ---
SWITCH_Z = 35.0            # top of shelf above the motor face
POST = 14.0                # square post
SHELF_T = 4.0
X_DIR = 1                  # +1 -> X lever points +X
# --- micro switch (SS-5 / KW12 style): body 20 x 10.2 x 6.4, 2 holes 9.5 apart ---
SW_L, SW_W = 20.0, 10.2
SW_HOLE_SPACING = 9.5
SW_HOLE = 1.9              # pilot for M2 self-tapping screw (2.2 if bolted with nuts)
SW_OFFSET = 15.0           # switch centre distance from post axis
SHELF_PAD = 3.0            # shelf margin around the switch
FILLET = 1.5
ACCESS_D = 7.0             # driver access hole in the shelf above each motor screw

reach = SW_OFFSET + SW_L / 2 + SHELF_PAD
shelf_w = SW_W + 2 * SHELF_PAD

# base plate along X, with the two motor holes
def rounded(solid):
    """Round the vertical edges of a block before it is joined to the rest."""
    return fillet(solid.edges().filter_by(Axis.Z), FILLET)

base = rounded(Pos(0, 0, BASE_T / 2) * Box(HOLE_SPACING + 2 * (MOTOR_SCREW / 2 + 4), BASE_W, BASE_T))
# post (between the holes, clear of the screw heads)
assert POST / 2 + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2, "post collides with screw heads"
post = Pos(0, 0, SWITCH_Z / 2) * Box(POST, POST, SWITCH_Z)

# shelf arms: +X for the X switch, -Y for the Y switch (top face at SWITCH_Z)
zc = SWITCH_Z - SHELF_T / 2
arm_x = rounded(Pos(X_DIR * (reach / 2), 0, zc) * Box(reach, shelf_w, SHELF_T))
arm_y = rounded(Pos(0, -reach / 2, zc) * Box(shelf_w, reach, SHELF_T))
part = base + post + arm_x + arm_y

# gussets under the shelf arms
def gusset(rot, length):
    prof = Polygon((0, 0), (length, 0), (0, SWITCH_Z - SHELF_T - BASE_T), align=None)
    g = extrude(Plane.XZ * prof, 3.0, both=True)
    return Pos(0, 0, BASE_T) * Rot(0, 0, rot) * Pos(POST / 2 - 1, 0, 0) * g
# only the Y arm gets a gusset: the X arm runs over a motor screw, which must stay reachable
part += gusset(-90, reach - POST / 2 - 4)

# motor screw holes
for sx in (-1, 1):
    part -= Pos(sx * HOLE_SPACING / 2, 0, BASE_T / 2) * Cylinder(MOTOR_SCREW / 2, BASE_T + 2)
    # screwdriver access through the shelf, straight above each motor screw
    part -= Pos(sx * HOLE_SPACING / 2, 0, SWITCH_Z - SHELF_T / 2) * Cylinder(ACCESS_D / 2, SHELF_T + 2)

# switch pilot holes (centred on each switch, spaced along its long axis)
hole = lambda: Cylinder(SW_HOLE / 2, SHELF_T + 2)
for s in (-1, 1):
    part -= Pos(X_DIR * SW_OFFSET + s * SW_HOLE_SPACING / 2, 0, zc) * hole()
    part -= Pos(0, -SW_OFFSET + s * SW_HOLE_SPACING / 2, zc) * hole()

bb = part.bounding_box()
print(f"volume {part.volume:.0f} mm3, bbox {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, valid={part.is_valid}")
export_step(part, "limit_switch_bracket.step")
export_stl(part, "limit_switch_bracket.stl")
