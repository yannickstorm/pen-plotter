#!/usr/bin/env python3
"""Browser tests for Plot Studio (studio.html), driven through headless Chrome with real input.

Run:  python3 tests/test_studio.py        (needs Chrome or Chromium — set $CHROME if it is not on PATH — and `pip install -r requirements-dev.txt`)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from cdp import Browser, serve  # noqa: E402

LOAD_WAVE = """(async () => {
  const T = window.__studio, blob = await (await fetch('tests/great-wave.webp')).blob();
  const src = await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(blob); });
  await T.addImage('great-wave', src);
  return T.items().length;
})()"""
SETTLE = "(async () => { for (let i = 0; i < 40; i++) { await __studio.runBuild(); await new Promise(r => setTimeout(r, 60)); } return 1; })()"
# item state in page (CSS px) coordinates
STATE = """(() => {
  const it = __studio.items().at(-1), r = document.getElementById('cv').getBoundingClientRect();
  const px = p => { const q = __studio.toPx(...p); return [q[0] + r.left, q[1] + r.top]; };
  return {w: it.w, h: it.w * it.aspect, geomW: it._geom && it._geom.w, handles: __studio.handles(it).map(h => px(h.p)),
          sel: __studio.selected() === it};
})()"""

failures = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


def near(a, b, tol=1.5):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


async def corner_tests(b, drag, label):
    """Drag corners the way people do (mostly along one axis) and check the box follows."""
    await b.js(LOAD_WAVE)
    await b.js(SETTLE)
    s = await b.js(STATE)
    check(s["sel"], f"{label}: imported object is selected")
    bl, br, tr, tl = s["handles"][:4]   # local (-,-) (+,-) (+,+) (-,+); Y up, so tr is on screen top-right

    # 1) top-right corner pulled straight up: top edge follows the pointer, bottom-left stays put
    target = [tr[0], tr[1] - 40]
    await drag(tr, target)
    s2 = await b.js(STATE)
    check(near(s2["handles"][0], bl, 0.5), f"{label}: opposite corner stays fixed")
    check(abs(s2["handles"][2][1] - target[1]) < 1.5, f"{label}: dragged corner is under the pointer vertically ({s2['handles'][2][1]:.1f} vs {target[1]:.1f})")
    check(abs(s2["h"] / s2["w"] - s["h"] / s["w"]) < 1e-6, f"{label}: proportions kept")
    check(s2["w"] > s["w"], f"{label}: object grew ({s['w']:.1f} → {s2['w']:.1f} mm)")

    # 2) same corner pulled sideways inwards: right edge follows, object shrinks
    tr2 = s2["handles"][2]
    target = [tr2[0] - 80, tr2[1]]
    await drag(tr2, target)
    s3 = await b.js(STATE)
    check(abs(s3["handles"][2][0] - target[0]) < 1.5, f"{label}: corner follows a sideways pull ({s3['handles'][2][0]:.1f} vs {target[0]:.1f})")
    check(s3["w"] < s2["w"], f"{label}: object shrank ({s2['w']:.1f} → {s3['w']:.1f} mm)")

    # 3) bottom-left corner: the top-right corner is now the fixed one
    bl3, tr3 = s3["handles"][0], s3["handles"][2]
    await drag(bl3, [bl3[0] - 30, bl3[1] + 10])
    s4 = await b.js(STATE)
    check(near(s4["handles"][2], tr3, 0.5), f"{label}: dragging the bottom-left corner keeps the top-right fixed")

    await b.js(SETTLE)
    s5 = await b.js(STATE)
    check(abs(s5["geomW"] - s5["w"]) < 1e-6, f"{label}: lines rebuilt at the new size")


async def desktop():
    print("desktop, mouse")
    b = await Browser(1400, 900).start()
    try:
        await b.goto(serve() + "/studio.html")
        await corner_tests(b, b.mouse_drag, "mouse")

        # edge handles stretch a rectangle in one direction only
        await b.js("__studio.addKind('rect')")
        await b.js(SETTLE)
        s = await b.js(STATE)
        right = s["handles"][4]
        await b.mouse_drag(right, [right[0] + 50, right[1]])
        s2 = await b.js(STATE)
        check(s2["w"] > s["w"] and abs(s2["h"] - s["h"]) < 1e-6, f"rect: side handle stretches width only ({s['w']:.1f}×{s['h']:.1f} → {s2['w']:.1f}×{s2['h']:.1f})")
        check(abs(s2["handles"][4][0] - right[0] - 50) < 1.5, "rect: side handle stays under the pointer")

        # multi-colour conversion of the Great Wave → G-code inside the bed
        res = await b.js("""(async () => {
          const T = window.__studio; T.items().length = 0; T.pens().length = 1;
          await T.addImage('great-wave', await (async () => { const blob = await (await fetch('tests/great-wave.webp')).blob();
            return new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(blob); }); })());
          const it = T.items()[0]; Object.assign(it.opts, {mode: 'colors', colors: 7, detail: 400});
          for (let i = 0; i < 40; i++) { await T.runBuild(); await new Promise(r => setTimeout(r, 60)); }
          const pens = T.activePens(), g = T.gcodeFor(pens, 'test');
          let out = 0, moves = 0;
          for (const l of g.split('\\n')) { const x = l.match(/X(-?[\\d.]+)/), y = l.match(/Y(-?[\\d.]+)/);
            if (x) { moves++; if (+x[1] < 0 || +x[1] > 310 || +y[1] < 0 || +y[1] > 210) out++; } }
          return {pens: pens.length, moves, out, pauses: (g.match(/^M0 /gm) || []).length};
        })()""")
        check(res["pens"] >= 3, f"great wave: colour separation uses {res['pens']} pens")
        check(res["moves"] > 1000 and res["out"] == 0, f"great wave: {res['moves']} moves, all inside the 310×210 bed")
        check(res["pauses"] == res["pens"] - 1, "great wave: one pen-change pause between pens")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()


def touch(*points):
    return [{"x": x, "y": y, "id": i + 1, "radiusX": 4, "radiusY": 4, "force": 1} for i, (x, y) in enumerate(points)]


async def phone():
    print("phone, touch")
    b = await Browser(390, 844, mobile=True).start()
    try:
        await b.goto(serve() + "/studio.html")
        await corner_tests(b, b.touch_drag, "touch")

        # browser bars sliding in/out resize the page mid-drag: nothing may jump
        s = await b.js(STATE)
        tr = s["handles"][2]
        target = [tr[0], tr[1] - 50]
        await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=touch(tr))
        for i in range(1, 13):
            if i == 4:
                await b.send("Emulation.setDeviceMetricsOverride", width=390, height=760, deviceScaleFactor=2, mobile=True)
                await asyncio.sleep(0.4)   # let layout and the canvas resize happen
            if i == 9:
                await b.send("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
                await asyncio.sleep(0.4)
            await asyncio.sleep(0.05)
            await b.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=touch([tr[0], tr[1] - 50 * i / 12]))
            if i == 6:   # while the page is shorter: the corner must still be under the finger
                await asyncio.sleep(0.3)
                mid = await b.js(STATE)
                check(near(mid["handles"][0], s["handles"][0], 0.5), f"page resize mid-drag: opposite corner doesn't jump while resized ({mid['handles'][0][1]:.1f} vs {s['handles'][0][1]:.1f})")
                check(abs(mid["handles"][2][1] - (tr[1] - 25)) < 1.5, f"page resize mid-drag: corner stays under the finger while resized ({mid['handles'][2][1]:.1f} vs {tr[1] - 25:.1f})")
        await b.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        await asyncio.sleep(0.3)
        s2 = await b.js(STATE)
        check(near(s2["handles"][0], s["handles"][0], 0.5), "page resize mid-drag: opposite corner stays put on screen")
        check(abs(s2["handles"][2][1] - target[1]) < 1.5, f"page resize mid-drag: corner ends under the finger ({s2['handles'][2][1]:.1f} vs {target[1]:.1f})")

        # a second finger landing during a resize keeps the resize instead of undoing it
        s = await b.js(STATE)
        tr = s["handles"][2]
        await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=touch(tr))
        for i in range(1, 7):
            await b.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=touch([tr[0] - 6 * i, tr[1]]))
        await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=touch([tr[0] - 36, tr[1]], [60, 600]))
        await b.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
        await asyncio.sleep(0.3)
        s2 = await b.js(STATE)
        check(s2["w"] < s["w"] - 1, f"second finger: resize kept ({s['w']:.1f} → {s2['w']:.1f} mm)")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()


async def main():
    await desktop()
    await phone()
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


asyncio.run(main())
