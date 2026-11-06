"""Write models/manifest.json: the list of parts that the Parts viewer artifact shows.

Drop a part into models/ as  NAME.stl  (shown in 3D)  plus any of  NAME.step  and other files starting with NAME.
An optional NAME.json sidecar gives {"name": "...", "description": "..."}.
Then run:  python build_manifest.py   and publish the artifact (parts/viewer.html + everything in models/).
"""
import json, pathlib, re, struct, time

here = pathlib.Path(__file__).parent / "models"

def stl_stats(path):
    """Bounding box (mm), volume (mm3) and triangle count of a binary or ASCII STL."""
    b = path.read_bytes()
    n = struct.unpack("<I", b[80:84])[0] if len(b) >= 84 else -1
    if len(b) == 84 + 50 * n:
        tris = [struct.unpack_from("<9f", b, 84 + 50 * i + 12) for i in range(n)]
    else:
        v = [float(x) for x in re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", b) for x in x]
        tris = [tuple(v[i:i + 9]) for i in range(0, len(v) - 8, 9)]
    xs = [t[k] for t in tris for k in (0, 3, 6)]; ys = [t[k] for t in tris for k in (1, 4, 7)]; zs = [t[k] for t in tris for k in (2, 5, 8)]
    vol = sum((t[0] * (t[4] * t[8] - t[5] * t[7]) - t[1] * (t[3] * t[8] - t[5] * t[6]) + t[2] * (t[3] * t[7] - t[4] * t[6])) / 6 for t in tris)
    return {"size": [round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2), round(max(zs) - min(zs), 2)],
            "volume_mm3": round(abs(vol), 1), "triangles": len(tris)}

models = []
for stl in sorted(here.glob("*.stl"), key=lambda p: -p.stat().st_mtime):
    stem = stl.stem
    meta = json.loads((here / f"{stem}.json").read_text()) if (here / f"{stem}.json").exists() else {}
    files = [p for p in sorted(here.glob(f"{stem}.*")) if p.suffix.lower() not in (".json",)]
    models.append({"id": re.sub(r"[^a-z0-9-]+", "-", stem.lower()).strip("-"), "name": meta.get("name", stem.replace("_", " ")),
                   "description": meta.get("description", ""), "stl": f"models/{stl.name}",
                   "files": [{"name": p.name, "path": f"models/{p.name}", "bytes": p.stat().st_size} for p in files],
                   "updated": time.strftime("%Y-%m-%d", time.localtime(stl.stat().st_mtime)), **stl_stats(stl)})
(here / "manifest.json").write_text(json.dumps({"models": models}, indent=1))
print(f"models/manifest.json: {len(models)} part(s): " + ", ".join(m["id"] for m in models))
