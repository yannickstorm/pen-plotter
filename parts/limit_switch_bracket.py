"""Limit-switch bracket for the X and Y endstops (all dimensions in mm).

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin.
Z is up. The base sits on the horizontal motor face; each switch sits on its own
horizontal shelf.
  * X switch: lever points +X (along the line of the two motor holes), shelf top at X_Z
  * Y switch: lever points -Y (rotated -90 deg), shelf top Y_DROP lower
X_TIP / Y_TIP = distance from the origin to the FRONT of the switch body (lever side).
Flip X_DIR to -1 if the X switch should point the other way.

Run:  python limit_switch_bracket.py   ->  limit_switch_bracket.step / .stl
"""
from build123d import *

# --- motor side (NEMA 17 face: holes 31 mm apart, M3) ---
HOLE_SPACING = 31.0
MOTOR_SCREW = 3.4          # clearance for M3
HEAD_D = 6.0               # M3 cap/pan head
BASE_T = 4.0               # base plate thickness
BASE_W = 12.0
# --- where the switches go ---
X_Z = 35.0                 # top of the X switch shelf above the motor face
Y_DROP = 10.0              # Y switch shelf is this much lower
Y_Z = X_Z - Y_DROP
X_TIP = 50.0               # front of X switch, from the origin along X
Y_TIP = 40.0               # front of Y switch, from the origin along -Y
X_DIR = 1                  # +1 -> X lever points +X
POST = 14.0                # square post between the motor screws
SHELF_T = 4.0
FILLET = 1.5
ACCESS_D = 6.0             # driver access hole in the X shelf above each motor screw
# --- micro switch (D2F-type): body ~12.8 x 5.8, 2 holes 6.5 apart (CHECK with calipers) ---
SW_L, SW_W = 12.8, 5.8
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.4              # pilot for M1.6 self-tapping screw (use ~1.7 to bolt through)
SHELF_PAD = 3.0            # shelf margin beside the switch
GUSSET_T = 2.0

sw_x = X_TIP - SW_L / 2    # switch centres
sw_y = Y_TIP - SW_L / 2
shelf_w = SW_W + 2 * SHELF_PAD
assert POST / 2 + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2, "post collides with screw heads"
assert sw_x - SW_HOLE_SPACING / 2 - SW_HOLE / 2 > HOLE_SPACING / 2 + ACCESS_D / 2 + 0.5, "switch holes hit access hole"

def rounded(solid):
    """Round the vertical edges of a block before it is joined to the rest."""
    return fillet(solid.edges().filter_by(Axis.Z), FILLET)

base = rounded(Pos(0, 0, BASE_T / 2) * Box(HOLE_SPACING + 2 * (MOTOR_SCREW / 2 + 4), BASE_W, BASE_T))
post = Pos(0, 0, X_Z / 2) * Box(POST, POST, X_Z)

# shelf arms start at the post axis
xz, yz = X_Z - SHELF_T / 2, Y_Z - SHELF_T / 2
arm_x = rounded(Pos(X_DIR * X_TIP / 2, 0, xz) * Box(X_TIP, shelf_w, SHELF_T))
arm_y = rounded(Pos(0, -Y_TIP / 2, yz) * Box(shelf_w, Y_TIP, SHELF_T))
part = base + post + arm_x + arm_y

def gusset(top_z, length, x, y, rot):
    """Triangle standing on the bed (z=0): tall edge against the post, foot running `length` outwards,
    hypotenuse up to the shelf underside. Local +X points away from the post; rotated by `rot` about Z."""
    h = top_z - SHELF_T
    prof = Polygon((0, 0), (length, 0), (0, h), align=None)
    g = extrude(Plane.XZ * prof, GUSSET_T / 2, both=True)
    return Pos(x, y, 0) * Rot(0, 0, rot) * Pos(POST / 2 - 1, 0, 0) * g

# Y arm: one gusset down its centre line
part += gusset(Y_Z, 26.0, 0, 0, -90)
# X arm runs over a motor screw: two gussets either side of it, clear of the screw heads
g_off = HEAD_D / 2 + 0.5 + GUSSET_T / 2
for sy in (-1, 1):
    part += gusset(X_Z, 30.0, 0, sy * g_off, 0 if X_DIR > 0 else 180)

# motor screw holes (through the base) and driver access through the X shelf
for sx in (-1, 1):
    part -= Pos(sx * HOLE_SPACING / 2, 0, BASE_T / 2) * Cylinder(MOTOR_SCREW / 2, BASE_T + 2)
    part -= Pos(sx * HOLE_SPACING / 2, 0, xz) * Cylinder(ACCESS_D / 2, SHELF_T + 2)

# switch pilot holes, spaced along each switch's long axis
hole = lambda z: Cylinder(SW_HOLE / 2, SHELF_T + 2)
for s in (-1, 1):
    part -= Pos(X_DIR * sw_x + s * SW_HOLE_SPACING / 2, 0, xz) * hole(xz)
    part -= Pos(0, -sw_y + s * SW_HOLE_SPACING / 2, yz) * hole(yz)

bb = part.bounding_box()
print(f"volume {part.volume:.0f} mm3, bbox {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, valid={part.is_valid}")
export_step(part, "limit_switch_bracket.step")
export_stl(part, "limit_switch_bracket.stl")
