# Pen plotter — notes for Claude

See README.md for what each file does. Machine: CoreXY, GRBL 1.1, servo pen (`M3 S0` up, `M3 S35` down), bed 310 × 210 mm.

## Plot Studio and its hosted copy

- `studio.html` is the source of truth. The claude.ai artifact is built from it; never edit the artifact on its own.
- Hosted copy: https://claude.ai/artifact/AujGupkM1J2GTmEN4L9aoj
- Tests: `python3 tests/test_studio.py` (cloud sessions get `websockets` and `$CHROME` from `.claude/hooks/session-start.sh`).

After changing `studio.html`:

1. Run the tests; they must all pass.
2. Commit.
3. Before publishing, read the live artifact. If it differs from a build of the previous commit (apart from the
   wrapper claude.ai adds), someone edited it elsewhere: merge those changes into `studio.html` first.
4. Build with `python3 build_artifact.py <scratchpad>/studio-artifact.html` and publish that file to the URL above,
   labelled with the short commit hash.
5. Push.
