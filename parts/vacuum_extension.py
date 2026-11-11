"""Vacuum cleaner extension: a short hollow tube with a push-in plug that fits the nozzle opening of the hand vacuum.

All sizes are ESTIMATES read off a photo (no scale in it): measure the nozzle opening and edit PLUG_W / PLUG_H.
Prints standing on its wide end (Z up), no supports: the shoulder and the plug get narrower going up, the top has a 45 degree lead-in.
Holding: the plug is made HOLE - CLEAR, and two crush ribs per wide face add RIB interference so it grips by friction.

    python vacuum_extension.py        ->  models/vacuum_extension.(step|stl) and a short test plug models/vacuum_extension_fit_test.(step|stl)
"""
import os
from build123d import *

HOLE_W = 42.0                  # measured inner width (long side) of the nozzle opening
HOLE_H_SIDES, HOLE_H_MID = 18.0, 20.0   # measured: one long side is curved out, 18 mm high at the ends, 20 mm in the middle
CLEAR = 0.2                    # gap to the hole so it slides in, before the ribs
RIB = 0.4                      # height of the crush ribs (extra grip, they squash a little)
PLUG_R = 3.0                   # corner radius of the plug
WALL = 2.0                     # wall of the plug (and tube)
LEAD = 1.5                     # 45 degree lead-in chamfer on the plug's top edge
BODY_L, PLUG_L = 65.0, 35.0    # tube length (stops against the nozzle) and plug length that goes in -> 100 mm in total
SAG = HOLE_H_MID - HOLE_H_SIDES

def prism(w, ybot, ysides, ymid, r, z0, length):
    """Cross-section: flat bottom at y=ybot, sides up to ysides, curved top bulging to ymid; extruded along Z, corners rounded."""
    with BuildPart() as p:
        with BuildSketch(Plane.XY.offset(z0)):
            with BuildLine():
                Polyline((-w / 2, ybot), (w / 2, ybot), (w / 2, ysides))
                ThreePointArc((w / 2, ysides), (0, ymid), (-w / 2, ysides))
                Line((-w / 2, ysides), (-w / 2, ybot))
            make_face()
        extrude(amount=length)
    part = p.part
    return fillet(part.edges().filter_by(Axis.Z), r)

def make(body_l, plug_l):
    c = CLEAR / 2
    pw = HOLE_W - CLEAR
    plug = prism(pw, c, HOLE_H_SIDES - c, HOLE_H_MID - c, PLUG_R, body_l, plug_l)
    body = prism(pw + 2 * WALL, c - WALL, HOLE_H_SIDES - c + WALL, HOLE_H_MID - c + WALL, PLUG_R + WALL, 0, body_l)
    part = body + plug
    top = part.edges().filter_by_position(Axis.Z, body_l + plug_l - 0.01, body_l + plug_l + 0.01)
    part = chamfer(top, LEAD)
    bore = prism(pw - 2 * WALL, c + WALL, HOLE_H_SIDES - c - WALL, HOLE_H_MID - c - WALL, PLUG_R - WALL, -1, body_l + plug_l + 2)
    part = part - bore                                           # the air channel straight through
    z0, z1 = body_l + 1.0, body_l + plug_l - 3.0                 # crush ribs on both wide faces, stopping short of the lead-in
    half = (pw / 2) ** 2
    R = ((pw / 2) ** 2 + SAG ** 2) / (2 * SAG)                   # radius of the curved side
    for x in (-pw / 4, pw / 4):
        part = part + Pos(x, c, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
        ytop = HOLE_H_MID - c - (R - (R * R - x * x) ** 0.5)
        part = part + Pos(x, ytop, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
    return part

if __name__ == "__main__":
    os.makedirs("models", exist_ok=True)
    for name, bl, pl in (("vacuum_extension", BODY_L, PLUG_L), ("vacuum_extension_fit_test", 4.0, 25.0)):
        part = make(bl, pl)
        bb = part.bounding_box()
        print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
        assert part.is_valid and abs(bb.size.Z - (bl + pl)) < 0.02 and len(part.solids()) == 1
        export_step(part, f"models/{name}.step")
        export_stl(part, f"models/{name}.stl", tolerance=0.01, angular_tolerance=0.1)
