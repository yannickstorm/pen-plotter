"""Build viewer.html: the arm and carrier STLs and key dimensions embedded in viewer_template.html.

    python build_viewer.py     (run limit_switch_bracket.py first so the STLs are current)
"""
import base64, json, re, pathlib

here = pathlib.Path(__file__).parent
src = (here / "limit_switch_bracket.py").read_text()
names = ["HOLE_SPACING", "STACK_DX", "STACK_DY", "Y_SIGN", "X_Z", "Y_DROP", "X_DIR", "SW_HOLE_SPACING", "ADJ", "ADJ_Z", "CLAMP_DIST", "TOP_T", "DT_H", "DT_CL"]
params = {n: float(re.search(rf"^{n}\s*=\s*(-?[\d.]+)", src, re.M).group(1)) for n in names}
m = re.search(r"^SW_L, SW_W, SW_H\s*=\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)", src, re.M)
params.update(SW_L=float(m.group(1)), SW_W=float(m.group(2)), SW_H=float(m.group(3)))
def stl_b64(name):
    stl = (here / name).read_bytes()
    assert len(stl) > 84 and len(stl) == 84 + 50 * int.from_bytes(stl[80:84], "little"), "STL must be binary"
    return base64.b64encode(stl).decode()
import math
sx = params["HOLE_SPACING"] / 2 + params["STACK_DX"]; sy = params["Y_SIGN"] * params["STACK_DY"]
L = math.hypot(sx, sy)
params["Z_CS_TOP"] = params["X_Z"] - params["TOP_T"]
params["Z_B"] = round(params["Z_CS_TOP"] - (params["DT_H"] + params["DT_CL"] + 1.7), 3)
params["CX"] = round(sx - params["CLAMP_DIST"] * sx / L, 3)     # clamp centre, unmirrored
params["CY"] = round(sy - params["CLAMP_DIST"] * sy / L, 3)
data = (f"const PARAMS = {json.dumps(params)};\n"
        f"const STL_ARM_B64 = \"{stl_b64('limit_switch_arm.stl')}\";\n"
        f"const STL_BRIDGE_B64 = \"{stl_b64('limit_switch_bridge.stl')}\";\n"
        f"const STL_CROSS_B64 = \"{stl_b64('limit_switch_cross.stl')}\";\n"
        f"const STL_CARRIER_B64 = \"{stl_b64('limit_switch_carrier.stl')}\";")
out = (here / "viewer_template.html").read_text().replace("/*DATA*/", data)
(here / "viewer.html").write_text(out)
print(f"viewer.html: {len(out) / 1e6:.2f} MB")
