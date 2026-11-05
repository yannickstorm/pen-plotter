"""Build viewer.html: the bracket's STL and key dimensions embedded in viewer_template.html.

    python build_viewer.py     (run limit_switch_bracket.py first so the STL is current)
"""
import base64, json, re, pathlib

here = pathlib.Path(__file__).parent
src = (here / "limit_switch_bracket.py").read_text()
names = ["HOLE_SPACING", "STACK_DX", "STACK_DY", "Y_SIGN", "X_Z", "Y_DROP", "X_DIR", "SW_HOLE_SPACING"]
params = {n: float(re.search(rf"^{n}\s*=\s*(-?[\d.]+)", src, re.M).group(1)) for n in names}
m = re.search(r"^SW_L, SW_W, SW_H\s*=\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", src, re.M)
params.update(SW_L=float(m.group(1)), SW_W=float(m.group(2)), SW_H=float(m.group(3)))
stl = (here / "limit_switch_bracket.stl").read_bytes()
assert len(stl) > 84 and len(stl) == 84 + 50 * int.from_bytes(stl[80:84], "little"), "STL must be binary"
data = f"const PARAMS = {json.dumps(params)};\nconst STL_B64 = \"{base64.b64encode(stl).decode()}\";"
out = (here / "viewer_template.html").read_text().replace("/*DATA*/", data)
(here / "viewer.html").write_text(out)
print(f"viewer.html: {len(out) / 1e6:.2f} MB")
