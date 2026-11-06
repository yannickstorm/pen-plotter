"""Build viewer.html: the base and Y arm STLs and key numbers embedded in viewer_template.html.

    python limit_switch_bracket.py   (writes the STLs and viewer_params.json)
    python build_viewer.py
"""
import base64, json, pathlib

here = pathlib.Path(__file__).parent
params = json.loads((here / "viewer_params.json").read_text())

def stl_b64(name):
    stl = (here / name).read_bytes()
    assert len(stl) > 84 and len(stl) == 84 + 50 * int.from_bytes(stl[80:84], "little"), "STL must be binary"
    return base64.b64encode(stl).decode()

data = (f"const PARAMS = {json.dumps(params)};\n"
        f"const STL_BASE_B64 = \"{stl_b64('limit_switch_base.stl')}\";\n"
        f"const STL_YARM_B64 = \"{stl_b64('limit_switch_yarm.stl')}\";")
out = (here / "viewer_template.html").read_text().replace("/*DATA*/", data)
(here / "viewer.html").write_text(out)
print(f"viewer.html: {len(out) / 1e6:.2f} MB")
