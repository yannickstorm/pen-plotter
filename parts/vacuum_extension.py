"""Vacuum cleaner extension: a short hollow tube. Front end = push-in plug that fits the nozzle opening of the hand vacuum;
back end = a socket of the SAME shape that takes the old brush extension.

The old extension's thin tongue (the part that goes in) ends in a wider collar that must NOT go in, and that collar is slanted:
at SLANT_DEG to the tongue axis, with its rounded side nearer the tip. So the socket's rim is cut at the same angle (the wall on the rounded
side is shorter) and the collar lands flat on it all the way round. The socket is also SOCKET_THIN mm thinner than the vacuum opening.

Prints standing on the plug end with the socket opening up, no supports: the socket floor (flat) faces up, the plug's top edge (on the bed) is a
45 degree chamfer, and the tube's shoulder over the plug is a 45 degree chamfer too.

    python vacuum_extension.py   ->  models/vacuum_extension.(step|stl) + short test pieces (fit_test = plug only, socket_test = socket only)
"""
import math
import os
from build123d import *

HOLE_W = 42.0                  # measured inner width (long side) of the nozzle opening
HOLE_H_SIDES, HOLE_H_MID = 18.0, 20.0   # measured: one long side is curved out, 18 mm high at the ends, 20 mm in the middle
CLEAR = 0.2                    # plug gap to the hole so it slides in, before the ribs
RIB = 0.4                      # height of the plug's crush ribs
PLUG_R = 3.0                   # corner radius of the plug
WALL = 1.5                     # wall of the plug and tube
LEAD = 0.6                     # 45 degree lead-in chamfer on the plug's tip
SOCKET_DEPTH = 23.0            # socket length along the axis; its floor is slanted parallel to the rim (measured: the adapter is only 23 mm long)
SLANT_DEG = 50.0               # angle between the old part's slanted collar and the tongue axis (measured ~45, "more like 50")
SOCKET_THIN = 3.0              # the socket is this much thinner (in the 18/20 mm direction) than the vacuum opening: the old tongue is thinner
SOCKET_CLEAR = 0.1             # per side, so the old part slides in
SOCKET_RIB = 0.3               # small crush ribs inside the socket for a snug fit
PLUG_L = 25.0                  # plug length that goes into the vacuum
SAG = HOLE_H_MID - HOLE_H_SIDES
# the tube is only as long as the socket needs: rim plane + depth at the deepest point (rounded side) + a 3 mm floor
BODY_L = math.ceil((HOLE_H_MID + SOCKET_CLEAR - SOCKET_THIN / 2 + SOCKET_CLEAR + WALL) / math.tan(math.radians(SLANT_DEG)) + SOCKET_DEPTH + 3.0)

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

def make(body_l, plug_l, depth=SOCKET_DEPTH):
    """Built with the body at the bottom (z=0) and the plug on top; flipped for printing in main()."""
    c, k = CLEAR / 2, SOCKET_CLEAR
    pw = HOLE_W - CLEAR
    plug = prism(pw, c, HOLE_H_SIDES - c, HOLE_H_MID - c, PLUG_R, body_l, plug_l)
    body = prism(HOLE_W + 2 * k + 2 * WALL, -k - WALL, HOLE_H_SIDES + k + WALL, HOLE_H_MID + k + WALL, PLUG_R + k + WALL, 0, body_l)
    body = chamfer(body.edges().filter_by_position(Axis.Z, body_l - 0.01, body_l + 0.01), WALL + 0.1)   # 45 degree shoulder: prints without support
    part = body + plug
    part = chamfer(part.edges().filter_by_position(Axis.Z, body_l + plug_l - 0.01, body_l + plug_l + 0.01), LEAD)
    T2 = SOCKET_THIN / 2
    bore = prism(pw - 2 * WALL, c + WALL, HOLE_H_SIDES + k - T2 - 0.6, HOLE_H_MID + k - T2 - 0.6, PLUG_R - WALL, -1, body_l + plug_l + 2)   # stays inside the thinner socket
    part = part - bore                                           # the air channel straight through
    if depth <= 0:
        return part
    # socket: `depth` long, rim AND floor both slanted at SLANT_DEG. The old part's thin tongue ends in a wider collar that must NOT go in
    # and sits at a slant, so the rim is cut at the same angle (the wall on the rounded side is shorter) and the collar lands flat on it.
    yf, yr = -k - WALL, HOLE_H_MID + k + WALL                    # outer faces of the tube on the flat and the rounded side
    zp = lambda y: (y - yf) / math.tan(math.radians(SLANT_DEG))  # rim plane at SLANT_DEG to the axis: z = 0 at the flat outer face, deeper towards the rounded side
    socket = prism(HOLE_W + 2 * k, -k + T2, HOLE_H_SIDES + k - T2, HOLE_H_MID + k - T2, PLUG_R + k, -1, body_l)
    with BuildPart() as fl:                                      # everything above the rim and below the slanted floor plane
        with BuildSketch(Plane.YZ):
            Polygon((-6, -2), (26, -2), (26, zp(26) + depth), (-6, zp(-6) + depth), align=None)
        extrude(amount=30, both=True)
    part = part - (socket & fl.part)
    with BuildPart() as w:                                       # the wedge above the slanted rim plane, cut away, as a wedge across X
        with BuildSketch(Plane.YZ):
            Polygon((-6, -2), (26, -2), (26, zp(26)), (-6, zp(-6)), align=None)
        extrude(amount=30, both=True)
    part = part - w.part
    Rs = ((HOLE_W / 2 + k) ** 2 + SAG ** 2) / (2 * SAG)
    for x in (-HOLE_W / 4, HOLE_W / 4):                          # small crush ribs inside, 2 mm in from the rim to 3 mm short of the floor
        for y in (-k + T2, HOLE_H_MID + k - T2 - (Rs - (Rs * Rs - x * x) ** 0.5)):
            z_lo, z_hi = zp(y) + 2.0, zp(y) + depth - 3.0
            if z_hi > z_lo:
                part = part + Pos(x, y, (z_lo + z_hi) / 2) * Box(1.2, 2 * SOCKET_RIB, z_hi - z_lo)
    z0, z1 = body_l + 1.0, body_l + plug_l - 3.0                 # plug crush ribs on both wide faces, stopping short of the lead-in
    R = ((pw / 2) ** 2 + SAG ** 2) / (2 * SAG)
    for x in (-pw / 4, pw / 4) if z1 > z0 else ():
        part = part + Pos(x, c, (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
        part = part + Pos(x, HOLE_H_MID - c - (R - (R * R - x * x) ** 0.5), (z0 + z1) / 2) * Box(1.2, 2 * RIB, z1 - z0)
    return part

if __name__ == "__main__":
    os.makedirs("models", exist_ok=True)
    for name, bl, pl, dr in (("vacuum_extension", BODY_L, PLUG_L, SOCKET_DEPTH),
                             ("vacuum_extension_fit_test", 4.0, 25.0, 0),
                             ("vacuum_extension_socket_test", BODY_L, 3.0, SOCKET_DEPTH)):
        part = make(bl, pl, dr)
        part = Pos(0, 0, bl + pl) * part.rotate(Axis.Y, 180)      # flip: plug end on the bed, socket opening up
        bb = part.bounding_box()
        print(f"{name}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, {part.volume:.0f} mm3, valid={part.is_valid}, z {bb.min.Z:.2f}..{bb.max.Z:.2f}")
        assert part.is_valid and abs(bb.size.Z - (bl + pl)) < 0.02 and abs(bb.min.Z) < 0.02 and len(part.solids()) == 1
        export_step(part, f"models/{name}.step")
        export_stl(part, f"models/{name}.stl", tolerance=0.01, angular_tolerance=0.1)
