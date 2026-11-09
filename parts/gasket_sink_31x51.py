"""Sink gasket, flat and thin with an up-turned sealing rim that prints without supports (mm).

A flat web WEB_T thick from the hole (ID) out to FLAT_TO, then a short curve (radius ARC_R on the web's centre line) turns
it up to 45 degrees, and a straight 45 degree ramp carries it to the outer edge (OD), where the rim meets the mating
surface. The underside is flat out to FLAT_TO and nowhere steeper than 45 degrees, so it prints without supports.
Print in TPU, flat side down.

Run:  python gasket_sink_31x51.py -> models/gasket_sink_31x51.step / .stl
"""
import math, os
from build123d import *

ID, OD = 31.0, 51.0
WEB_T = 1.2        # thickness of the web (measured along its normal everywhere)
FLAT_TO = 22.0     # the web stays flat out to this radius
ARC_R = 2.5        # radius of the curve on the web's centre line
TURN_DEG = 45.0    # steepest angle: the limit for printing without supports

th = math.radians(TURN_DEG)
ri, ro = ID / 2, OD / 2
ru, rt = ARC_R + WEB_T / 2, ARC_R - WEB_T / 2        # radius of the underside / top surface of the curve
ls = (ro - FLAT_TO - ru * math.sin(th)) / math.cos(th)   # length of the straight ramp, so the underside ends at OD
assert ls >= 0 and rt > 0, "the curve does not fit between FLAT_TO and the outer edge"
r0, zc = FLAT_TO, WEB_T / 2 + ARC_R                  # where the curve starts, height of its centre
def arc_pt(rad, a): return (r0 + rad * math.sin(a), zc - rad * math.cos(a))
def ramp(p): return (p[0] + ls * math.cos(th), p[1] + ls * math.sin(th))
u0, u1 = arc_pt(ru, th), arc_pt(rt, th)
with BuildSketch(Plane.XZ) as sk:
    with BuildLine():
        Line((ri, 0), (r0, 0))
        ThreePointArc((r0, 0), arc_pt(ru, th / 2), u0)          # underside, curving up
        Line(u0, ramp(u0))                                       # underside, straight 45 degree ramp
        Line(ramp(u0), ramp(u1))                                 # rim face, along the web's normal
        Line(ramp(u1), u1)                                       # top surface ramp, back down
        ThreePointArc(u1, arc_pt(rt, th / 2), (r0, WEB_T))       # top surface, curve back to the flat
        Line((r0, WEB_T), (ri, WEB_T))
        Line((ri, WEB_T), (ri, 0))
    make_face()
part = revolve(sk.sketch, axis=Axis.Z)
bb = part.bounding_box()
print(f"gasket: dia {bb.size.X:g}, height {bb.size.Z:.2f} mm, flat to r={r0:g}, ramp {ls:.2f} mm long, {part.volume:.0f} mm3, valid={part.is_valid}")
assert abs(bb.size.X - OD) < 0.02 and part.is_valid
os.makedirs("models", exist_ok=True)
export_step(part, "models/gasket_sink_31x51.step")
export_stl(part, "models/gasket_sink_31x51.stl", tolerance=0.01, angular_tolerance=0.1)
