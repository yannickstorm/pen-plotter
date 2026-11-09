"""Bar 5 x 4 x 30 mm (X x Y x Z): the 5 x 2 x 30 bar made twice as wide in Y.
Prints flat on its 30 x 5 face (4 mm tall), no supports.

Run:  python bar_5x4x30.py -> models/bar_5x4x30.step / .stl
"""
import os
from build123d import *

LENGTH_X, WIDTH_Y, HEIGHT_Z = 5.0, 4.0, 30.0
part = Box(LENGTH_X, WIDTH_Y, HEIGHT_Z, align=(Align.MIN, Align.MIN, Align.MIN))
bb = part.bounding_box()
assert abs(bb.size.X - LENGTH_X) < 1e-6 and abs(bb.size.Y - WIDTH_Y) < 1e-6 and abs(bb.size.Z - HEIGHT_Z) < 1e-6
assert part.is_valid and len(part.solids()) == 1
print(f"bar: {bb.size.X:g} x {bb.size.Y:g} x {bb.size.Z:g} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
os.makedirs("models", exist_ok=True)
export_step(part, "models/bar_5x4x30.step")
export_stl(part, "models/bar_5x4x30.stl")
