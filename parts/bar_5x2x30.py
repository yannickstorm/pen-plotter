"""A plain bar, 5 x 2 x 30 mm (X x Y x Z). Prints best lying flat on its 30 x 5 face (2 mm tall).

Run:  python bar_5x2x30.py -> models/bar_5x2x30.step / .stl
"""
from build123d import *

LENGTH_X, WIDTH_Y, HEIGHT_Z = 5.0, 2.0, 30.0
part = Box(LENGTH_X, WIDTH_Y, HEIGHT_Z, align=(Align.MIN, Align.MIN, Align.MIN))
bb = part.bounding_box()
print(f"bar: {bb.size.X:g} x {bb.size.Y:g} x {bb.size.Z:g} mm, {part.volume:.0f} mm3, valid={part.is_valid}")
import os
os.makedirs("models", exist_ok=True)
export_step(part, "models/bar_5x2x30.step")
export_stl(part, "models/bar_5x2x30.stl")
