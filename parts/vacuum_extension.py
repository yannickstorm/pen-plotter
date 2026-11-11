"""Vacuum cleaner extension: a short hollow tube. Front end = push-in plug that fits the nozzle opening of the hand vacuum;
back end = a socket of the SAME shape that takes the old brush extension.

The old extension's tongue has a slanted end: its rounded side is SLANT mm longer than its flat side (measured: it bottomed on the
rounded side 15 mm before the flat side). The socket floor is slanted to match, so the old part seats fully.

Prints standing on the plug end with the socket opening up, no supports: the socket floor faces up, the plug's top edge (on the bed) is a
45 degree chamfer, and the tube's shoulder over the plug is a 45 degree chamfer too.

    python vacuum_extension.py   ->  models/vacuum_extension.(step|stl) + short test pieces (fit_test = plug only, socket_test = socket only)
"""
import os
from build123d import *

HOLE_W = 42.0                  # measured inner width (long side) of the nozzle opening
HOLE_H_SIDES, HOLE_H_MID = 18.0, 20.0   # measured: one long side is curved out, 18 mm high at the ends, 20 mm in the middle
CLEAR = 0.2                    # plug gap to the hole so it slides in, before the ribs
RIB = 0.4                      # height of the plug's crush ribs
PLUG_R = 3.0                   # corner radius of the plug
WALL = 2.0                     # wall of the plug and tube
LEAD = 0.8                     # 45 degree lead-in chamfer on the plug's tip
SOCKET_DEPTH_ROUND = 30.0      # socket depth measured on the rounded side (where the old tongue is longest)
SLANT = 15.0                   # the flat side of the old tongue is this much shorter than the rounded side
SOCKET_CLEAR = 0.1             # per side, so the old part slides in
SOCKET_RIB = 0.3               # small crush ribs inside the socket for a snug fit
BODY_L, PLUG_L = 65.0, 35.0    # tube length and plug length -> 100 mm in total
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
    return fillet(p.part.edges().filter_by(Axis.Z), r)

def make(body_l, plug_l, depth_round=SOCKET_DEPTH_ROUND, slant=SLANT):
    """Built with the body at the bottom (z=0) and the plug on top; flipped for printing in main()."""
    c, k = CLEAR / 2, SOCKET_CLEAR
    pw = HOLE_W - CLEAR
    plug = prism(pw, c, HOLE_H_SIDES - c, HOLE_H_MID - c, PLUG_R, body_l, plug_l)
    body = prism(HOLE_W + 2 * k + 2 * WALL, -k - WALL, HOLE_H_SIDES + k + WALL, HOLE_H_MID + k + WALL, PLUG_R + k + WALL, 0, body_l)
    body = chamfer(body.edges().filter_by_position(Axis.Z, body_l - 0.01, body_l + 0.01), WALL + 0.1)   # 45 degree shoulder: prints without support
    part = body + plug
    part = chamfer(part.edges().filter_by_position(Axis.Z, body_l + plug_l - 0.01, body_l + plug_l + 0.01), LEAD)
    bore = prism(pw - 2 * WALL, c + WALL, HOLE_H_SIDES - c - WALL, HOLE_H_MID - c - WALL, PLUG_R - WALL, -1, body_l + plug_l + 2)
    part = part - bore                                           # the air channel straight through
    if depth_round <= 0:
        return part
    # socket: floor slants from depth_round on the rounded side (y = HOLE_H_MID + k) to depth_round - slant on the flat side (y = -k)
    y0, y1 = -k, HOLE_H_MID + k
    zf = lambda y: depth_round - slant + slant * (y - y0) / (y1 - y0)
    socket = prism(HOLE_W + 2 * k, -k, HOLE_H_SIDES + k, HOLE_H_MID + k, PLUG_R + k, -1, depth_round + 2)
    with BuildPart() as w:                                       # the space under the slanted floor, as a wedge across X
        with BuildSketch(Plane.YZ):
            Polygon((-6, -2), (26, -2), (26, zf(26)), (-6, zf(-6)), align=None)
        extrude(amount=30, both=True)
    part = part - (socket & w.part)
    Rs = ((HOLE_W / 2 + k) ** 2 + SAG ** 2) / (2 * SAG)
    for x in (-HOLE_W / 4, HOLE_W / 4):                          # small crush ribs inside, from 2 mm in to 3 mm short of the floor
        for y in (-k, HOLE_H_MID + k - (Rs - (Rs * Rs - x * x) ** 0.5)):
            top = zf(y) - 3.0
            if top > 2.0:
                part = part + Pos(x, y, (2.0 + top) / 2) * Box(1.2, 2 * SOCKET_RIB, top - 2.0)
    z0, z1 = body_l + 1.0, body_l + plug_l - 3.0                 # plug crush ribs on both wide faces, stopping short of the lead-in
    R = ((pw / 2) ** 2 + SAG ** 2) / (2 * SAG)
    for x in (-pw / 4, pw / 4) if z1 > z0 else ():
        part = part + Pos(x, c, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
        part = part + Pos(x, HOLE_H_MID - c - (R - (R * R - x * x) ** 0.5), (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
    return part

if __name__ == "__main__":
    os.makedirs("models", exist_ok=True)
    for name, bl, pl, dr in (("vacuum_extension", BODY_L, PLUG_L, SOCKET_DEPTH_ROUND),
                             ("vacuum_extension_fit_test", 4.0, 25.0, 0),
                             ("vacuum_extension_socket_test", SOCKET_DEPTH_ROUND + 4.0, 3.0, SOCKET_DEPTH_ROUND)):
        part = make(bl, pl, dr)
        part = Pos(0, 0, bl + pl) * part.rotate(Axis.Y, 180)      # flip: plug end on the bed, socket opening up
        bb = part.bounding_box()
        print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume:.0f} mm3, valid={part.is_valid}, z {bb.min.Z:.2f}..{bb.max.Z:.2f}")
        assert part.is_valid and abs(bb.size.Z - (bl + pl)) < 0.02 and abs(bb.min.Z) < 0.02 and len(part.solids()) == 1
        export_step(part, f"models/{name}.step")
        export_stl(part, f"models/{name}.stl", tolerance=0.01, angular_tolerance=0.1)
