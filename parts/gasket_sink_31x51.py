"""Sink gasket: ring, 31 mm inner diameter, 51 mm outer diameter. Flat underside; the top slopes from THICK at the
inner edge down to RIM_T at the outer edge, where it meets the flat. A recess of RECESS_D diameter in the flat
side thins the ring around the hole to about 2 mm (1.76 to 2.0 mm over the recess) (mm).

Print in TPU (flexible), flat side down, 100 % infill if it must seal.

Run:  python gasket_sink_31x51.py -> models/gasket_sink_31x51.step / .stl
"""
import os
from build123d import *

ID, OD = 31.0, 51.0
THICK = 3.0      # thickness at the inner edge
RIM_T = 0.6      # thickness left at the outer edge (a true knife edge cannot be printed)
RECESS_D = 33.0  # recess in the flat side, concentric with the hole
RECESS_DEPTH = 1.0   # leaves 2.0 mm at the hole's edge and 1.76 mm at the recess edge (the top slopes)

ri, ro = ID / 2, OD / 2
profile = Polygon((ri, 0), (ro, 0), (ro, RIM_T), (ri, THICK), align=None)        # (radius, height)
part = revolve(Plane.XZ * profile, axis=Axis.Z)
part -= Pos(0, 0, RECESS_DEPTH / 2 - 0.5) * Cylinder(RECESS_D / 2, RECESS_DEPTH + 1)      # recess from the flat side
bb = part.bounding_box()
print(f"gasket: dia {bb.size.X:g}, height {bb.size.Z:g} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
assert abs(bb.size.X - OD) < 0.01 and abs(bb.size.Z - THICK) < 0.01 and part.is_valid
top = lambda r: THICK - (THICK - RIM_T) * (r - ri) / (ro - ri)
print(f"thickness over the recess: {top(ri) - RECESS_DEPTH:.2f} mm at the hole, {top(RECESS_D / 2) - RECESS_DEPTH:.2f} mm at the recess edge")
os.makedirs("models", exist_ok=True)
export_step(part, "models/gasket_sink_31x51.step")
export_stl(part, "models/gasket_sink_31x51.stl", tolerance=0.01, angular_tolerance=0.1)
