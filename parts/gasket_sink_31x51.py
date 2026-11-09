"""Sink gasket, flat with a tall up-turned sealing rim that prints without supports (mm).

A flat web WEB_T thick from the hole (ID) out to FLAT_TO, then a straight 45 degree ramp up to the outer edge (OD),
where the rim meets the mating surface; the rim's top edge is RIM_H high. The UNDERSIDE has a sharp bend from the flat
onto the ramp, so no surface leans less than 45 degrees from horizontal and it prints without supports (a gentle curve
lifting off the bed would be a shallow overhang). The TOP side is rounded with TOP_R where the web turns up, because
nothing overhangs there; that is the curve that helps the seal.
Print in TPU, flat side down.

Run:  python gasket_sink_31x51.py -> models/gasket_sink_31x51.step / .stl
"""
import math, os
from build123d import *

ID, OD = 31.0, 51.0
WEB_T = 1.2        # thickness of the web and of the ramp (measured along its normal)
RIM_H = 5.0        # height of the rim's top edge above the flat underside
TOP_R = 3.0        # radius of the curve on the top side where the web turns up

c = math.sqrt(0.5)                                         # cos 45 = sin 45
ri, ro = ID / 2, OD / 2
ez = RIM_H - WEB_T * c                                     # height where the underside ramp ends, at OD
r0 = ro - ez                                               # the underside is flat out to here (45 degree ramp: run = rise)
assert r0 > ri + 2 * TOP_R * math.tan(math.radians(22.5)) + 1.0, "ramp does not fit: lower RIM_H or TOP_R"
e = (ro, ez)                                               # underside end
te = (ro - WEB_T * c, ez + WEB_T * c)                      # top end of the rim face (along the ramp's normal)
ts = (r0 - WEB_T * c, WEB_T * c)                           # top ramp line starts here ...
t_flat = ts[0] + (WEB_T - ts[1]) / c * c                   # ... and reaches the web's top (z = WEB_T) here
with BuildSketch(Plane.XZ) as sk:
    Polygon((ri, 0), (r0, 0), e, te, (t_flat, WEB_T), (ri, WEB_T), align=None)
part = revolve(sk.sketch, axis=Axis.Z)
corner = [ed for ed in part.edges().filter_by(GeomType.CIRCLE) if abs(ed.radius - t_flat) < 0.05]
assert len(corner) == 1, "top corner edge not found"
part = fillet(corner, TOP_R)                               # smooth the top where the web turns up
bb = part.bounding_box()
print(f"gasket: dia {bb.size.X:g}, height {bb.size.Z:.2f} mm, underside flat out to r={r0:.2f}, {part.volume:.0f} mm3, valid={part.is_valid}")
assert abs(bb.size.X - OD) < 0.02 and part.is_valid and abs(bb.size.Z - RIM_H) < 0.02
os.makedirs("models", exist_ok=True)
export_step(part, "models/gasket_sink_31x51.step")
export_stl(part, "models/gasket_sink_31x51.stl", tolerance=0.01, angular_tolerance=0.1)
