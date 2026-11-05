"""Limit-switch bracket: two stacked micro switches carried out on an arm from the motor screws (mm).

Frame: the two NEMA mounting holes lie on the X axis, centred on the origin; Z is up.
The "front" screw is the one on the side the X lever points to: (X_DIR * HOLE_SPACING/2, 0).
The switch stack sits STACK_DX along X and STACK_DY along Y from that screw.
  * X switch: lever points +X, top shelf (shelf top at X_Z)
  * Y switch: same spot but Y_DROP lower, lever points -Y (-90 deg)
Both are mounted flat (screws vertical). Fit the lower (Y) switch first: its screws
are reached through two access holes in the upper shelf.

Run:  python limit_switch_bracket.py   ->  limit_switch_bracket.step / .stl
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
# --- where the switches go ---
X_DIR = 1                  # +1: front screw / X lever on the +X side (-1 mirrors the whole part)
STACK_DX = 50.0            # from the front screw, along the lever direction
STACK_DY = 40.0            # from the front screw, sideways (sign below)
Y_SIGN = 1                 # +1: stack is on the +Y side (Y lever then points back towards the motor line)
X_Z = 35.0                 # top of the X shelf above the motor face
Y_DROP = 10.0              # Y shelf top is this much lower
TOP_T = 3.0                # thickness of the upper structure (beam + X shelf)
Y_SHELF_T = 4.0
BEAM_W = 12.0
WEB_T = 2.5
# --- micro switch (D2F-type): body ~12.8 x 5.8 x 6.5, 2 holes 6.5 apart (CHECK with calipers) ---
SW_L, SW_W, SW_H = 12.8, 5.8, 6.5
SW_HOLE_SPACING = 6.5
SW_HOLE = 1.4              # pilot for M1.6 self-tapping screw
SCREW_HEAD = 3.6           # hole in the upper shelf for the lower switch's screws
PAD = 3.0
FILLET = 1.0

Y_Z = X_Z - Y_DROP
assert Y_Z + SW_H + 0.3 < X_Z - TOP_T, "lower switch would touch the upper shelf"
assert POST / 2 + 0.5 < HOLE_SPACING / 2 - HEAD_D / 2, "post collides with screw heads"

def rounded(solid, r=FILLET):
    return fillet(solid.edges().filter_by(Axis.Z), r)

# stack centre (built for X_DIR=+1, mirrored at the end)
sx = HOLE_SPACING / 2 + STACK_DX
sy = Y_SIGN * STACK_DY

base = rounded(Pos(0, 0, BASE_T / 2) * Box(HOLE_SPACING + 2 * (MOTOR_SCREW / 2 + 4), BASE_W, BASE_T), 1.5)
post = Pos(0, 0, X_Z / 2) * Box(POST, POST, X_Z)

# upper structure: diagonal beam from the post to the stack, plus the X-switch shelf
L = math.hypot(sx, sy)
th = math.atan2(sy, sx)
ux, uy = math.cos(th), math.sin(th)
nx, ny = -uy, ux
h = BEAM_W / 2
beam_pts = [(-h * nx, -h * ny), (L * ux - h * nx, L * uy - h * ny), (L * ux + h * nx, L * uy + h * ny), (h * nx, h * ny)]
top_z0 = X_Z - TOP_T
beam = extrude(Plane.XY.offset(top_z0) * Polygon(*beam_pts, align=None), amount=TOP_T)

# X shelf: front edge flush with the switch front (x = sx + SW_L/2), margin behind and to the sides
x_lo, x_hi = sx - SW_L / 2 - PAD, sx + SW_L / 2
y_lo, y_hi = sy - SW_W / 2 - PAD, sy + SW_L / 2 + PAD     # extends back (+Y) to hold the lower shelf's wall
xshelf = rounded(Pos((x_lo + x_hi) / 2, (y_lo + y_hi) / 2, X_Z - TOP_T / 2) * Box(x_hi - x_lo, y_hi - y_lo, TOP_T))

# lower (Y) shelf: front edge flush with the switch front (y = sy - SW_L/2), wall behind it up to the X shelf
yx_lo, yx_hi = sx - SW_W / 2 - PAD, sx + SW_W / 2 + PAD
yy_lo, yy_hi = sy - SW_L / 2, sy + SW_L / 2 + PAD
yshelf = rounded(Pos((yx_lo + yx_hi) / 2, (yy_lo + yy_hi) / 2, Y_Z - Y_SHELF_T / 2) * Box(yx_hi - yx_lo, yy_hi - yy_lo, Y_SHELF_T))
wall_y0 = sy + SW_L / 2
wall = Pos((yx_lo + yx_hi) / 2, (wall_y0 + yy_hi) / 2, ((Y_Z - Y_SHELF_T) + X_Z) / 2) * Box(yx_hi - yx_lo, yy_hi - wall_y0, X_Z - (Y_Z - Y_SHELF_T))

part = base + post + beam + xshelf + yshelf + wall

# vertical web under the beam: stands on the bed, trapezoid with a sloping end
web_top = L - 24.0
web_foot = 24.0
prof = Polygon((0, 0), (web_foot, 0), (web_top, X_Z - TOP_T), (0, X_Z - TOP_T), align=None)
web = Rot(0, 0, math.degrees(th)) * extrude(Plane.XZ * prof, WEB_T / 2, both=True)
part += web

# motor screw holes
for k in (-1, 1):
    part -= Pos(k * HOLE_SPACING / 2, 0, BASE_T / 2) * Cylinder(MOTOR_SCREW / 2, BASE_T + 2)
# X switch pilot holes (spaced along X)
for k in (-1, 1):
    part -= Pos(sx - SW_L / 2 + SW_L / 2 + k * SW_HOLE_SPACING / 2, sy, X_Z - TOP_T / 2) * Cylinder(SW_HOLE / 2, TOP_T + 2)
# Y switch pilot holes (spaced along Y), and access holes above them in the X shelf
for k in (-1, 1):
    yy = sy + k * SW_HOLE_SPACING / 2
    part -= Pos(sx, yy, Y_Z - Y_SHELF_T / 2) * Cylinder(SW_HOLE / 2, Y_SHELF_T + 2)
    part -= Pos(sx, yy, X_Z - TOP_T / 2) * Cylinder(SCREW_HEAD / 2, TOP_T + 2)

if X_DIR < 0:
    part = mirror(part, Plane.YZ)

# sanity: the web must stay clear of the front motor screw head
d = abs(HOLE_SPACING / 2 * uy)          # perpendicular distance from the beam axis to the front screw
print(f"web-to-front-screw clearance: {d - WEB_T / 2 - HEAD_D / 2:.1f} mm")
bb = part.bounding_box()
print(f"stack at ({sx:.1f}, {sy:.1f}) from motor-hole centre; volume {part.volume:.0f} mm3, "
      f"bbox {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, valid={part.is_valid}, solids={len(part.solids())}")
export_step(part, "limit_switch_bracket.step")
export_stl(part, "limit_switch_bracket.stl")
