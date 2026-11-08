"""Sink gasket, flat and thin with an up-turned sealing rim (mm).

A flat web WEB_T thick from the hole (ID) out to R_FLAT, then the web curves upward on a circular arc (radius ARC_R on
its centre line) through TURN_DEG to the outer edge (OD), so the rim meets the mating surface at an angle and seals.
The underside is flat out to R_FLAT, then curves up with the web (at most TURN_DEG from horizontal, so it prints without
supports). Print in TPU, flat side down.

Run:  python gasket_sink_31x51.py -> models/gasket_sink_31x51.step / .stl
"""
import math, os
from build123d import *

ID, OD = 31.0, 51.0
WEB_T = 1.2        # thickness of the web
ARC_R = 7.0        # radius of the up-turn on the web's centre line
TURN_DEG = 40.0    # how far the rim has turned up at the outer edge

th = math.radians(TURN_DEG)
ri, ro = ID / 2, OD / 2
ru, rt = ARC_R + WEB_T / 2, ARC_R - WEB_T / 2        # radius of the underside / top surface of the arc
r0 = ro - ru * math.sin(th)                          # where the flat part ends, so the underside ends at the outer diameter
zc = WEB_T / 2 + ARC_R                               # height of the arc's centre
def arc_pt(rad, a): return (r0 + rad * math.sin(a), zc - rad * math.cos(a))
mid = th / 2
with BuildSketch(Plane.XZ) as sk:
    with BuildLine():
        Line((ri, 0), (r0, 0))
        ThreePointArc((r0, 0), arc_pt(ru, mid), arc_pt(ru, th))        # underside, curving up
        Line(arc_pt(ru, th), arc_pt(rt, th))                           # rim face, along the arc's normal
        ThreePointArc(arc_pt(rt, th), arc_pt(rt, mid), (r0, WEB_T))    # top surface, back down to the flat
        Line((r0, WEB_T), (ri, WEB_T))
        Line((ri, WEB_T), (ri, 0))
    make_face()
part = revolve(sk.sketch, axis=Axis.Z)
bb = part.bounding_box()
print(f"gasket: dia {bb.size.X:g}, height {bb.size.Z:.2f} mm, flat web out to r={r0:.1f}, {part.volume:.0f} mm3, valid={part.is_valid}")
assert abs(bb.size.X - OD) < 0.02 and part.is_valid and r0 > ri
os.makedirs("models", exist_ok=True)
export_step(part, "models/gasket_sink_31x51.step")
export_stl(part, "models/gasket_sink_31x51.stl", tolerance=0.01, angular_tolerance=0.1)
