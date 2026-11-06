"""Print check: put each part in its print orientation and list what would need supports.

    python check_print.py

Overhang = a downward-facing surface steeper than about 48 degrees from vertical (45 degree slopes are fine) that is not on the bed. Regions with a
span of at most BRIDGE mm in their narrowest direction are counted as bridges (they print fine without supports).
"""
import sys
import numpy as np
import trimesh

BRIDGE = 15.0
# service frame (x, y, z up) -> print frame (z up). Rotations only, so the part is never mirrored.
Rx = lambda deg: trimesh.transformations.rotation_matrix(np.radians(deg), [1, 0, 0])
ORIENT = {
    "arm":     ("flat, as designed (base on the bed)",    np.eye(4)),
    "cross":   ("upside down, top face on the bed",       Rx(180)),
    "carrier": ("upside down, upper plate on the bed",    Rx(180)),
}

def regions(mesh, mask):
    """Connected groups of masked faces."""
    idx = np.flatnonzero(mask)
    if not len(idx):
        return []
    sel = set(idx.tolist())
    adj = {}
    for a, b in mesh.face_adjacency:
        if a in sel and b in sel:
            adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    seen, out = set(), []
    for f in idx:
        if f in seen:
            continue
        stack, comp = [f], []
        seen.add(f)
        while stack:
            c = stack.pop(); comp.append(c)
            for nb in adj.get(c, []):
                if nb not in seen:
                    seen.add(nb); stack.append(nb)
        out.append(comp)
    return out

def check(name, path):
    desc, T = ORIENT[name]
    m = trimesh.load(path)
    m.apply_transform(T)
    m.apply_translation([0, 0, -m.bounds[0][2]])
    n, c, a = m.face_normals, m.triangles_center, m.area_faces
    down = (n[:, 2] < -0.75) & (c[:, 2] > 0.05)      # steeper than ~48 degrees from vertical: 45 degree dovetail flanks pass
    bed = (n[:, 2] < -0.99) & (c[:, 2] <= 0.05)
    support, bridges = 0.0, 0.0
    worst = []
    for comp in regions(m, down):
        tri = m.triangles[comp].reshape(-1, 3)
        ext = tri.max(0) - tri.min(0)
        span = sorted(ext[:2])[0]            # narrowest horizontal extent
        area = a[comp].sum()
        if span <= BRIDGE or area < 1.0:
            bridges += area
        else:
            support += area; worst.append((area, ext))
    bb = m.extents
    print(f"{name:8s} {desc}")
    print(f"         {bb[0]:.0f} x {bb[1]:.0f} x {bb[2]:.0f} mm tall {bb[2]:.0f}, bed contact {a[bed].sum():.0f} mm2, "
          f"needs support {support:.0f} mm2, bridges {bridges:.0f} mm2, volume {m.volume/1000:.1f} cm3")
    for area, ext in sorted(worst, key=lambda w: -w[0])[:4]:
        print(f"           unsupported region {area:.0f} mm2 ({ext[0]:.0f} x {ext[1]:.0f} mm)")
    return support

if __name__ == "__main__":
    tot = sum(check(n, f"limit_switch_{n}.stl") for n in ORIENT)
    print(f"total needing support: {tot:.0f} mm2")
