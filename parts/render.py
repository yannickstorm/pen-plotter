"""Render an STL to a 4-view PNG (iso, top, front, right) with flat shading."""
import sys, numpy as np, trimesh, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

m = trimesh.load(sys.argv[1]); out = sys.argv[2]
tris = m.vertices[m.faces]; n = m.face_normals
light = np.array([0.4, -0.6, 0.7]); light /= np.linalg.norm(light)
shade = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
colors = np.c_[0.30 * shade, 0.55 * shade, 0.85 * shade, np.ones_like(shade)]
lo, hi = m.bounds; c = (lo + hi) / 2; r = (hi - lo).max() / 2
views = [("iso", 25, -55), ("top", 90, -90), ("front", 0, -90), ("right", 0, 0)]
fig = plt.figure(figsize=(10, 10))
for i, (name, el, az) in enumerate(views):
    ax = fig.add_subplot(2, 2, i + 1, projection="3d")
    ax.add_collection3d(Poly3DCollection(tris, facecolors=colors, edgecolors=(0, 0, 0, 0.08), linewidths=0.2))
    for s, f in zip((c - r, c + r), ()): pass
    ax.set_xlim(c[0] - r, c[0] + r); ax.set_ylim(c[1] - r, c[1] + r); ax.set_zlim(c[2] - r, c[2] + r)
    ax.set_box_aspect((1, 1, 1)); ax.view_init(el, az)
    ax.set_proj_type("ortho" if name != "iso" else "persp")
    ax.set_title(name); ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
fig.suptitle(f"{sys.argv[1]}  —  {hi[0]-lo[0]:.1f} × {hi[1]-lo[1]:.1f} × {hi[2]-lo[2]:.1f} mm")
plt.tight_layout(); plt.savefig(out, dpi=80)
