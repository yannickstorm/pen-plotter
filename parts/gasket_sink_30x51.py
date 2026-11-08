"""Sink gasket: ring, 30 mm inner diameter, 51 mm outer diameter (mm).

Flat underside. The top side has a recess (diameter RECESS_D, concentric with the hole) whose flat floor leaves the ring
RECESS_T thick around the hole. Around the recess is a raised lip THICK high; from the lip the top slopes down to
RIM_T at the outer edge, where it meets the flat.

Print in TPU (flexible), flat side down, 100 % infill if it must seal.

Run:  python gasket_sink_30x51.py -> models/gasket_sink_30x51.step / .stl
"""
import os
from build123d import *

ID, OD = 30.0, 51.0
THICK = 3.0       # maximum thickness: the lip at the recess edge
RIM_T = 0.6       # thickness left at the outer edge (a true knife edge cannot be printed)
RECESS_D = 35.0   # recess in the top (sloped) side, concentric with the hole
RECESS_T = 2.0    # thickness left over the recess (1.8 to 2 mm asked for)

ri, rr, ro = ID / 2, RECESS_D / 2, OD / 2
profile = Polygon((ri, 0), (ro, 0), (ro, RIM_T), (rr, THICK), (rr, RECESS_T), (ri, RECESS_T), align=None)   # (radius, height)
part = revolve(Plane.XZ * profile, axis=Axis.Z)
bb = part.bounding_box()
print(f"gasket: dia {bb.size.X:g}, max height {bb.size.Z:g} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
assert abs(bb.size.X - OD) < 0.01 and abs(bb.size.Z - THICK) < 0.01 and part.is_valid and ri < rr < ro
os.makedirs("models", exist_ok=True)
export_step(part, "models/gasket_sink_30x51.step")
export_stl(part, "models/gasket_sink_30x51.stl", tolerance=0.01, angular_tolerance=0.1)
