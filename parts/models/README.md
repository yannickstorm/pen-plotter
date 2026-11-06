# Parts folder

Everything here is shown by the **Parts Viewer** artifact (`parts/viewer.html`) and can be downloaded from it as a zip.

To add a part (Claude does this when you ask for one):

1. Export `NAME.stl` (shown in 3D) and, if you have it, `NAME.step` into this folder. Any other file called `NAME.*` goes into the zip as well.
2. Optionally add `NAME.json` with `{"name": "Readable name", "description": "What it is"}`.
3. Run `python parts/build_manifest.py` (writes `models/manifest.json` with sizes and volumes).
4. Republish the artifact: `parts/viewer.html` plus the files in `models/` (the page reads `models/manifest.json`).

The page lists the newest part first. STL and STEP cannot be saved directly from an artifact, so each download is a zip.
