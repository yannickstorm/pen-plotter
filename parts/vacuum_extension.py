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
SOCKET_L = 30.0               # depth of the socket in the back end, for the old brush extension (same shape as the nozzle opening)
SOCKET_CLEAR = 0.1             # per side, so the old part slides in
SOCKET_RIB = 0.3               # small crush ribs inside the socket for a snug fit
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

def cone(w, ybot, ysides, ymid, r, z0, length, taper):
    """Like prism() but narrowing upward at `taper` degrees (the socket ceiling, so it prints without a flat overhang)."""
    with BuildPart() as p:
        with BuildSketch(Plane.XY.offset(z0)) as sk:
            with BuildLine():
                Polyline((-w / 2, ybot), (w / 2, ybot), (w / 2, ysides))
                ThreePointArc((w / 2, ysides), (0, ymid), (-w / 2, ysides))
                Line((-w / 2, ysides), (-w / 2, ybot))
            make_face()
            fillet(sk.vertices(), r)
        extrude(amount=length, taper=taper)
    return p.part

def make(body_l, plug_l, socket_l=SOCKET_L):
    c = CLEAR / 2
    pw = HOLE_W - CLEAR
    plug = prism(pw, c, HOLE_H_SIDES - c, HOLE_H_MID - c, PLUG_R, body_l, plug_l)
    k = SOCKET_CLEAR                                              # socket = nozzle opening + clearance; body wall WALL around it
    body = prism(HOLE_W + 2 * k + 2 * WALL, -k - WALL, HOLE_H_SIDES + k + WALL, HOLE_H_MID + k + WALL, PLUG_R + k + WALL, 0, body_l)
    part = body + plug
    top = part.edges().filter_by_position(Axis.Z, body_l + plug_l - 0.01, body_l + plug_l + 0.01)
    part = chamfer(top, LEAD)
    bore = prism(pw - 2 * WALL, c + WALL, HOLE_H_SIDES - c - WALL, HOLE_H_MID - c - WALL, PLUG_R - WALL, -1, body_l + plug_l + 2)
    part = part - bore                                           # the air channel straight through
    if socket_l <= 0:
        return part
    socket = prism(HOLE_W + 2 * k, -k, HOLE_H_SIDES + k, HOLE_H_MID + k, PLUG_R + k, -1, socket_l + 1)
    part = part - socket
    part = part - cone(HOLE_W + 2 * k, -k, HOLE_H_SIDES + k, HOLE_H_MID + k, PLUG_R + k, socket_l, 2.25, 45)
    Rs = ((HOLE_W / 2 + k) ** 2 + SAG ** 2) / (2 * SAG)
    for x in (-HOLE_W / 4, HOLE_W / 4):
        zc, zl = 2.0 + (socket_l - 3.0) / 2, socket_l - 3.0       # ribs start 2 mm in, stop 1 mm short of the ceiling
        part = part + Pos(x, -k, zc) * Box(1.2, 2 * SOCKET_RIB, zl)
        yt = HOLE_H_MID + k - (Rs - (Rs * Rs - x * x) ** 0.5)
        part = part + Pos(x, yt, zc) * Box(1.2, 2 * SOCKET_RIB, zl)
    z0, z1 = body_l + 1.0, body_l + plug_l - 3.0                 # crush ribs on both wide faces, stopping short of the lead-in
    half = (pw / 2) ** 2
    R = ((pw / 2) ** 2 + SAG ** 2) / (2 * SAG)                   # radius of the curved side
    for x in (-pw / 4, pw / 4) if z1 > z0 else ():
        part = part + Pos(x, c, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
        ytop = HOLE_H_MID - c - (R - (R * R - x * x) ** 0.5)
        part = part + Pos(x, ytop, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
    return part

if __name__ == "__main__":
    os.makedirs("models", exist_ok=True)
    for name, bl, pl, sl in (("vacuum_extension", BODY_L, PLUG_L, SOCKET_L), ("vacuum_extension_fit_test", 4.0, 25.0, 0), ("vacuum_extension_socket_test", SOCKET_L + 3.0, 3.0, SOCKET_L)):
        part = make(bl, pl, sl)
        bb = part.bounding_box()
        print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
        assert part.is_valid and abs(bb.size.Z - (bl + pl)) < 0.02 and len(part.solids()) == 1
        export_step(part, f"models/{name}.step")
        export_stl(part, f"models/{name}.stl", tolerance=0.01, angular_tolerance=0.1)
