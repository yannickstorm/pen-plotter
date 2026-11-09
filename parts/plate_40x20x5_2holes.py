"""Flat plate 40 x 20 x 5 mm with two 4 mm through holes, 30 mm apart, centred on the long (X) axis.
Prints flat (5 mm tall), no supports needed.

Run:  python plate_40x20x5_2holes.py -> models/plate_40x20x5_2holes.step / .stl
"""
import os
from build123d import *

LENGTH_X, WIDTH_Y, THICK_Z = 40.0, 20.0, 5.0
HOLE_D = 4.0
HOLE_SPACING = 30.0

with BuildPart() as bp:
    Box(LENGTH_X, WIDTH_Y, THICK_Z, align=(Align.CENTER, Align.CENTER, Align.MIN))
    with Locations((-HOLE_SPACING / 2, 0, 0), (HOLE_SPACING / 2, 0, 0)):
        Hole(HOLE_D / 2)
part = bp.part

bb = part.bounding_box()
assert abs(bb.size.X - LENGTH_X) < 1e-6 and abs(bb.size.Y - WIDTH_Y) < 1e-6 and abs(bb.size.Z - THICK_Z) < 1e-6
assert part.is_valid and len(part.solids()) == 1
print(f"plate: {bb.size.X:g} x {bb.size.Y:g} x {bb.size.Z:g} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
os.makedirs("models", exist_ok=True)
export_step(part, "models/plate_40x20x5_2holes.step")
export_stl(part, "models/plate_40x20x5_2holes.stl")
