"""Vacuum cleaner extension: a short hollow tube with a push-in plug that fits the nozzle opening of the hand vacuum.

All sizes are ESTIMATES read off a photo (no scale in it): measure the nozzle opening and edit PLUG_W / PLUG_H.
Prints standing on its wide end (Z up), no supports: the shoulder and the plug get narrower going up, the top has a 45 degree lead-in.
Holding: the plug is made HOLE - CLEAR, and two crush ribs per wide face add RIB interference so it grips by friction.

    python vacuum_extension.py        ->  models/vacuum_extension.(step|stl) and a short test plug models/vacuum_extension_fit_test.(step|stl)
"""
import os
from build123d import *

HOLE_W, HOLE_H = 32.0, 16.0   # estimated inner size of the vacuum's nozzle opening (long side, short side)
CLEAR = 0.2                    # gap to the hole so it slides in, before the ribs
RIB = 0.4                      # height of the crush ribs (extra grip, they squash a little)
PLUG_W, PLUG_H = HOLE_W - CLEAR, HOLE_H - CLEAR
PLUG_R = 3.0                   # corner radius of the plug
WALL = 2.0                     # wall of the plug (and tube)
BODY_W, BODY_H, BODY_R = PLUG_W + 2 * WALL, PLUG_H + 2 * WALL, PLUG_R + WALL
BORE_W, BORE_H, BORE_R = PLUG_W - 2 * WALL, PLUG_H - 2 * WALL, PLUG_R - WALL
LEAD = 1.5                     # 45 degree lead-in chamfer on the plug's top edge
BODY_L, PLUG_L = 65.0, 35.0    # tube length (stops against the nozzle) and plug length that goes in -> 100 mm in total

def make(body_l, plug_l):
    with BuildPart() as p:
        with BuildSketch(Plane.XY):
            RectangleRounded(BODY_W, BODY_H, BODY_R)
        extrude(amount=body_l)
        with BuildSketch(Plane.XY.offset(body_l)):
            RectangleRounded(PLUG_W, PLUG_H, PLUG_R)
        extrude(amount=plug_l)
    part = p.part
    top = part.edges().filter_by_position(Axis.Z, body_l + plug_l - 0.01, body_l + plug_l + 0.01)
    part = chamfer(top, LEAD)
    with BuildPart() as c:                                      # the air channel straight through
        with BuildSketch(Plane.XY.offset(-1)):
            RectangleRounded(BORE_W, BORE_H, BORE_R)
        extrude(amount=body_l + plug_l + 2)
    part = part - c.part
    z0, z1 = body_l + 1.0, body_l + plug_l - 3.0                # crush ribs on both wide faces, stopping short of the lead-in
    for sy in (-1, 1):
        for x in (-PLUG_W / 4, PLUG_W / 4):
            part = part + Pos(x, sy * PLUG_H / 2, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
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
