#!/usr/bin/env python3
"""Browser tests for Plot Studio (studio.html), driven through headless Chrome with real input.

Run:  python3 tests/test_studio.py        (needs google-chrome and the `websockets` package)
"""
import asyncio
import json
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


# A city map with made-up streets (no network): reloads are counted instead of downloaded.
MAP_SETUP = """(async () => {
  const T = __studio; T.items().length = 0;
  document.getElementById('btnAdd').click(); document.querySelector('[data-add="style:city"]').click();
  const it = T.items().find(i => i.kind === 'style'), lat = 54.79, lon = 9.43, minor = [];
  for (let k = -40; k <= 40; k++) { minor.push([[-2000, k * 50], [2000, k * 50]]); minor.push([[k * 50, -2000], [k * 50, 2000]]); }
  Object.assign(it.opts, {lat, lon, km: 3, place: 'Testort'});
  const city = {R: 3 * 500 * GEO_MARGIN, minor, counts: {}};
  for (const k of ['major', 'service', 'paths', 'rail', 'river', 'waterRings', 'buildings', 'coast', 'piers', 'greenRings', 'trails', 'peaks', 'huts']) city[k] = [];
  it.geo = {kind: 'city', lat, lon, km: 3, place: 'Testort', city};
  window.__reloads = 0; window.geoReload = async () => { window.__reloads++; };
  T.select(it); fitView();
  for (let i = 0; i < 20; i++) { await T.runBuild(); await new Promise(r => setTimeout(r, 40)); }
  return 1;
})()"""
# screen point (page px) ↔ the place on the map under it
MAP_STATE = """(() => {
  const it = __studio.selected(), F = geoFrame(it), r = document.getElementById('cv').getBoundingClientRect();
  const c = __studio.toPx(...xform(it)([F.cx, F.cy]));
  return {cx: c[0] + r.left, cy: c[1] + r.top, rpx: F.r * V.k, km: it.opts.km, lat: it.opts.lat, lon: it.opts.lon,
          edit: mapEdit === it, covered: geoCovered(it), reloads: window.__reloads, viewK: V.k};
})()"""
MAP_AT = """(([x, y]) => { const it = __studio.selected(), r = document.getElementById('cv').getBoundingClientRect();
  return geoFrame(it).toLL(...worldToLocal(it, ...toW(x - r.left, y - r.top))); })"""


async def map_drag_checks(b, drag, label):
    """Map mode: a drag moves the map inside its frame and the place under the pointer stays under it."""
    s = await b.js(MAP_STATE)
    check(s["edit"], f"{label}: map mode is on")
    a = [s["cx"], s["cy"]]; z = [a[0] + 0.06 * s["rpx"], a[1] - 0.04 * s["rpx"]]   # small move: inside the downloaded margin
    before = await b.js(MAP_AT + f"({a})")
    await drag(a, z)
    await asyncio.sleep(0.6)
    after = await b.js(MAP_AT + f"({z})")
    s2 = await b.js(MAP_STATE)
    check(abs(before[0] - after[0]) < 1e-6 and abs(before[1] - after[1]) < 1e-6, f"{label}: the place under the pointer moves with it")
    check(s2["lat"] != s["lat"] and s2["covered"] and s2["reloads"] == 0, f"{label}: small move needs no reload")
    check(abs(s2["viewK"] - s["viewK"]) < 1e-9, f"{label}: the sheet view itself did not move or zoom")
    await drag([s2["cx"], s2["cy"]], [s2["cx"] - 0.6 * s2["rpx"], s2["cy"]])   # far: past the margin
    await asyncio.sleep(1.6)
    s3 = await b.js(MAP_STATE)
    check(not s3["covered"] and s3["reloads"] == 1, f"{label}: moving past the downloaded area reloads by itself ({s3['reloads']} reload)")


async def map_tests_mouse(b):
    await b.js(MAP_SETUP)
    s = await b.js(MAP_STATE)
    check(not s["edit"], "map: not in map mode after adding")
    # double-click the map → map mode
    for n in (1, 2):
        await b.send("Input.dispatchMouseEvent", type="mousePressed", x=s["cx"], y=s["cy"], button="left", buttons=1, clickCount=n)
        await b.send("Input.dispatchMouseEvent", type="mouseReleased", x=s["cx"], y=s["cy"], button="left", buttons=0, clickCount=n)
    await asyncio.sleep(0.2)
    await map_drag_checks(b, b.mouse_drag, "map, mouse")
    # wheel zooms the map around the pointer
    s = await b.js(MAP_STATE)
    p = [round(s["cx"] + 0.3 * s["rpx"]), round(s["cy"] + 0.2 * s["rpx"])]   # wheel events report whole pixels
    before = await b.js(MAP_AT + f"({p})")
    for _ in range(3):
        await b.send("Input.dispatchMouseEvent", type="mouseWheel", x=p[0], y=p[1], deltaX=0, deltaY=-100)
    await asyncio.sleep(0.6)
    after = await b.js(MAP_AT + f"({p})")
    s2 = await b.js(MAP_STATE)
    check(s2["km"] < s["km"] * 0.75, f"map, wheel: zoomed in ({s['km']} → {s2['km']} km)")
    err = max(abs(before[0] - after[0]), abs(before[1] - after[1])) * 111000
    check(err < 0.1, f"map, wheel: the place under the pointer stays put (off by {err:.3f} m)")
    check(abs(s2["viewK"] - s["viewK"]) < 1e-9, "map, wheel: the sheet view did not zoom")
    await b.send("Input.dispatchKeyEvent", type="keyDown", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    await b.send("Input.dispatchKeyEvent", type="keyUp", key="Escape", code="Escape", windowsVirtualKeyCode=27)
    s3 = await b.js(MAP_STATE)
    check(not s3["edit"], "map: Esc leaves map mode")
    check(not b.errors, f"map: no page errors {b.errors[:3]}")


async def map_tests_touch(b):
    await b.js(MAP_SETUP)
    await b.js("document.getElementById('mEdit').click()")
    await map_drag_checks(b, b.touch_drag, "map, touch")
    # two fingers spread apart: the map zooms in, the sheet view stays
    s = await b.js(MAP_STATE)
    c, d0, d1 = [s["cx"], s["cy"]], 0.2 * s["rpx"], 0.4 * s["rpx"]
    await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=touch([c[0] - d0, c[1]]))
    await b.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=touch([c[0] - d0, c[1]], [c[0] + d0, c[1]]))
    for i in range(1, 9):
        d = d0 + (d1 - d0) * i / 8
        await b.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=touch([c[0] - d, c[1]], [c[0] + d, c[1]]))
    await b.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])
    await asyncio.sleep(0.6)
    s2 = await b.js(MAP_STATE)
    check(abs(s2["km"] / s["km"] - 0.5) < 0.02, f"map, pinch: spreading two fingers zooms the map ({s['km']} → {s2['km']} km)")
    check(abs(s2["viewK"] - s["viewK"]) < 1e-9, "map, pinch: the sheet view did not zoom")
    check(not b.errors, f"map, touch: no page errors {b.errors[:3]}")


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
        await map_tests_mouse(b)
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
        await map_tests_touch(b)
    finally:
        await b.close()


# ---------- plotting on the demo plotter: live view, crash, recovery, resume ----------
WAIT = """(async (cond, ms) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (eval(cond)) return true; await new Promise(r => setTimeout(r, 40)); } return false; })"""
# every pen-down move of the job must be on the demo plotter's paper (it lays ink where the pen physically went)
INK_COVERS = """(async () => {
  const T = __studio, d = (await T.usb().api('job')).job, I = T.demo().ink, key = (a, b, c, e) => [a, b, c, e].map(v => v.toFixed(2)).join();
  const have = new Set(); for (let i = 0; i < I.length; i += 4) have.add(key(I[i], I[i + 1], I[i + 2], I[i + 3]));
  let miss = 0, n = 0; const M = d.moves;
  for (let i = 1; i < M.length; i++) if (M[i][3]) { n++; if (!have.has(key(M[i - 1][1], M[i - 1][2], M[i][1], M[i][2]))) miss++; }
  return {n, miss};
})()"""


async def wait(b, cond, ms=20000):
    return await b.js(f"{WAIT}({cond!r}, {ms})")


async def click(b, sel):
    """Click an element the way a person does (real mouse events at its centre), once it is there and enabled."""
    await wait(b, f"(e => e && !e.disabled)(document.querySelector({sel!r}))", 8000)
    r = await b.js(f"(() => {{ const e = document.querySelector({sel!r}); if (!e) return null; e.scrollIntoView({{block: 'center'}}); const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }})()")
    if not r:
        raise RuntimeError(f"nothing to click: {sel}")
    await b.mouse("mouseMoved", *r)
    await b.mouse("mousePressed", *r, buttons=1)
    await b.mouse("mouseReleased", *r)
    await asyncio.sleep(0.15)


async def plot_until_crash(b, frac):
    await wait(b, f"__studio.curJob() && __studio.curJob().running && __studio.curJob().progress > {frac}")
    # crash with the pen down, part-way through a stroke
    await wait(b, "__studio.demo().cur && __studio.demo().cur.down && __studio.demo().cur.t > 0.3")


async def plotting():
    print("plotting on the demo plotter")
    b = await Browser(1400, 900).start()
    base = serve()
    try:
        await b.goto(base + "/studio.html")
        # the studio's resume rules match the bridge's
        sys.path.insert(0, str(Path(__file__).parent.parent / "bridge"))
        sys.path.insert(0, str(Path(__file__).parent))
        import bridge as B
        from test_bridge import make_job
        g, _ = make_job(12, 4, seed=3)
        lines = B.clean_lines(g)
        js = await b.js(f"""(() => {{ const L = __studio.cleanLines({json.dumps(g)});
          return {{lines: L, starts: __studio.strokeStarts(L, 0), points: L.map((_, d) => __studio.resumePoint(L, d, 0)), pre: __studio.resumePreamble(L, 30, 0)}}; }})()""")
        check(js["lines"] == lines, "cleaned lines match the bridge")
        check(js["starts"] == B.stroke_starts(lines, 0), "stroke starts match the bridge")
        check(js["points"] == [B.resume_point(lines, d, 0) for d in range(len(lines))], "resume points match the bridge for every line")
        check(js["pre"] == B.resume_preamble(lines, 30, 0), f"resume preamble matches the bridge {js['pre']}")

        await b.js("__studio.addKind('pattern')")
        await b.js(SETTLE)
        # workspaces: each shows its own panels; the design can't be edited from Plot
        await click(b, "#wsSeg [data-ws=machine]")
        vis = await b.js("[...document.querySelectorAll('.app > [data-ws]')].filter(e => getComputedStyle(e).display !== 'none').map(e => e.dataset.ws)")
        check(vis == ["machine", "machine"], f"Machine shows only machine panels {vis}")
        check(await b.js("getComputedStyle(document.getElementById('btnExport')).display === 'none'"), "design-only buttons are hidden outside Design")
        await click(b, "[data-mc=demo]")
        check(await wait(b, "__studio.server().st && __studio.server().st.connected", 8000), "demo plotter connects")
        await click(b, "#wsSeg [data-ws=plot]")
        check(await b.js("__studio.ws()") == "plot", "Plot workspace")
        await click(b, "[data-p=go]")
        await plot_until_crash(b, 0.3)
        before = await b.js("__studio.curJob().done")
        await b.js("__studio.demo().crash()")
        check(await wait(b, "__studio.curJob() && __studio.curJob().state === 'interrupted'", 5000), "power glitch mid-plot → interrupted")
        j = await b.js("__studio.curJob()")
        check(j["resumable"] and j["done"] >= before, f"saved progress kept ({j['done']} of {j['total']} lines)")
        await wait(b, "__studio.live.strokes && document.getElementById('recCard').textContent.includes('stopped at')", 5000)
        rec = await b.js("""(() => { const c = document.getElementById('recCard'); return {shown: !c.hidden, text: c.textContent,
          start: __studio.live.strokes.includes(__studio.curJob().resume_at) || __studio.curJob().resume_at === __studio.curJob().done}; })()""")
        check(rec["shown"] and "controller reset" in rec["text"], "recovery card explains what happened")
        check("stopped at" in rec["text"], f"and warns that the controller lost its position: {rec['text'][:400]!r}")
        check(rec["start"] and j["resume_at"] <= j["done"], f"resumes at the start of the interrupted stroke (line {j['resume_at']}, done {j['done']})")
        await click(b, "[data-p=rhome]")
        check(await wait(b, "Math.hypot(...__studio.server().st.pos.slice(0, 2)) < 1e-6 && __studio.demo().offset[0] === 0", 5000), "Home puts it back at 0,0")
        await b.js("__studio.demo().speed = 200")
        await click(b, "[data-p=rgo]")
        check(await wait(b, "__studio.curJob().state === 'finished'", 30000), "resumed plot finishes")
        ink = await b.js(INK_COVERS)
        check(ink["n"] > 50 and ink["miss"] == 0, f"every line of the plan is on the paper ({ink['n']} moves, {ink['miss']} missing)")
        check(await b.js("__studio.session().done.size === 1"), "the pen is marked done")

        # the tab closes mid-plot: the design and the plot come back
        await click(b, "[data-p=redo]")
        await b.js("__studio.demo().newSheet()")
        await click(b, "[data-p=go]")
        await plot_until_crash(b, 0.25)
        await b.js("__studio.usb().pause()")     # hold still while the demo plotter's paper is saved
        await asyncio.sleep(3.5)
        done = await b.js("__studio.curJob().done")
        await b.goto(base + "/studio.html")
        check(await wait(b, "__studio.booted()", 10000), "reloaded")
        check(await b.js("__studio.items().length === 1 && __studio.items()[0].kind === 'pattern'"), "the design is restored")
        j = await b.js("__studio.curJob()")
        check(j and j["offline"] and j["resumable"] and j["done"] >= done - 5, f"the unfinished plot is found in this browser ({j and j['done']} lines)")
        check(await b.js("__studio.ws()") == "plot", "and opens in Plot")
        await click(b, "[data-p=cmach]")
        check(await wait(b, "__studio.server().st && __studio.server().st.connected && __studio.curJob().resumable && !__studio.curJob().offline", 8000), "reconnecting adopts it")
        await wait(b, "__studio.live.strokes", 5000)
        await click(b, "[data-p=rhome]")
        await wait(b, "__studio.demo().offset[0] === 0", 5000)
        await b.js("__studio.demo().speed = 200")
        await click(b, "[data-p=rgo]")
        check(await wait(b, "__studio.curJob().state === 'finished'", 30000), "resumed after the reload, and finished")
        ink = await b.js(INK_COVERS)
        check(ink["miss"] == 0, f"every line on the paper after the reload ({ink['miss']} missing)")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()


async def on_bridge():
    """The studio served by a Plotter Bridge (running here on a simulated GRBL): plot, crash, recover, resume."""
    print("plotting through the Plotter Bridge")
    import tempfile
    import threading
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, str(Path(__file__).parent.parent / "bridge"))
    import bridge as B
    from test_bridge import FakeGrbl, new_bridge
    P = new_bridge(tempfile.mkdtemp(), move_time=0.12)
    P.connect()
    B.Handler.plotter, B.Handler.token = P, None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), B.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    b = await Browser(1400, 900).start()
    try:
        await b.goto(f"http://127.0.0.1:{srv.server_address[1]}/studio")
        check(await wait(b, "__studio.conn().kind === 'bridge' && __studio.server().st && __studio.server().st.connected", 8000), "the studio on the bridge connects to it by itself")
        await b.js("__studio.addKind('star')")
        await b.js(SETTLE)
        await click(b, "#wsSeg [data-ws=plot]")
        await click(b, "[data-p=go]")
        check(await wait(b, "__studio.curJob() && __studio.curJob().running && __studio.curJob().progress > 0.25"), "plotting through the bridge, progress shows live")
        check(await wait(b, "__studio.live.moves && __studio.live.moves.length > 10", 5000), "the live view has the job's moves from the bridge")
        fake = FakeGrbl.instances[-1]
        for _ in range(400):   # crash while the star is being drawn
            if fake.cur and fake.cur[3] and len(fake.ink) >= 3:
                break
            await asyncio.sleep(0.01)
        drawn = len(fake.ink)
        fake.crash()
        check(await wait(b, "__studio.curJob().state === 'interrupted' && document.getElementById('recCard').textContent.includes('stopped at')", 8000),
              "controller reset → the recovery card, with the position warning")
        await click(b, "[data-p=rhome]")
        await wait(b, "Math.hypot(...__studio.server().st.pos.slice(0, 2)) < 1e-6", 5000)
        await click(b, "[data-p=rgo]")
        j = await b.js("__studio.curJob()")
        check(j["resume_from"] < j["total"] and drawn >= 3, f"crashed mid-stroke ({drawn} segments drawn), resumed from the stroke's start (line {j['resume_from'] + 1})")
        check(await wait(b, "__studio.curJob().state === 'finished'", 30000), "resumed through the bridge and finished")
        M = P.job["moves"]
        have = {tuple(round(v, 2) for v in seg) for seg in fake.ink}
        miss = [i for i in range(1, len(M)) if M[i][3] and (round(M[i - 1][1], 2), round(M[i - 1][2], 2), round(M[i][1], 2), round(M[i][2], 2)) not in have]
        check(not miss, f"every line is on the paper ({len(miss)} missing)")
        check(await b.js("__studio.session().done.size === 1"), "the pen is marked done")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()
        srv.shutdown()
        P.disconnect()


async def setv(b, sel, value):
    """Type into a field: set it and fire the input event, as the browser does for each keystroke."""
    await b.js(f"(() => {{ const e = document.querySelector({sel!r}); e.value = {json.dumps(str(value))}; e.dispatchEvent(new Event('input', {{bubbles: true}})); }})()")


async def machines_wizard():
    print("machines and the setup wizard")
    import tempfile
    import threading
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, str(Path(__file__).parent.parent / "bridge"))
    import bridge as B
    from test_bridge import new_bridge
    P = new_bridge(tempfile.mkdtemp(), move_time=0.01)
    P.connect()
    B.Handler.plotter, B.Handler.token = P, None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), B.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    bridge = f"127.0.0.1:{srv.server_address[1]}"
    base = serve()
    a = await Browser(1400, 900).start()
    c = None
    try:
        await a.goto(base + "/studio.html")
        await click(a, "#wsSeg [data-ws=machine]")
        check(await a.js("!!document.querySelector('#machList .empty')"), "no machines yet: the list invites you to add one")

        # --- the wizard with the demo plotter
        await click(a, "[data-mc=add]")
        await click(a, "[data-wz=via][data-v=demo]")
        await click(a, "[data-wz=next]")
        check(await wait(a, "__studio.wizard() && __studio.wizard().step === 1", 8000), "wizard: connected, on the detect step")
        check(await wait(a, "document.getElementById('modal').textContent.includes('GRBL 1.1h')", 8000), "detect: reads the firmware from the plotter")
        check(await a.js("document.getElementById('modal').textContent.includes('310 × 210')"), "detect: and the work area GRBL reports")
        check(await a.js("document.getElementById('modalBg').classList.contains('docked')"), "the wizard is docked beside the bed, not over it")
        await click(a, "[data-wz=next]")
        await setv(a, "#wzN_down", 30)
        check(await wait(a, "document.getElementById('conLog').textContent.includes('M3 S30')", 4000), "pen step: moving the slider sends the pen there live")
        check(await a.js("__studio.wizard().d.profile.down === 30 && __studio.demo().pen.down === 30"), "pen step: the value is kept")
        await click(a, "[data-wz=next]")
        await a.js("__studio.demo().speed = 200; __studio.demo().newSheet()")
        await click(a, "[data-wz=mark]")
        MARK = "(() => { const d = __studio.demo(), x = []; for (let i = 0; i < d.ink.length; i += 2) x.push(d.ink[i]); return {n: d.ink.length / 4, min: Math.min(...x), max: Math.max(...x)}; })()"
        DRAWN = "(__studio.demo().ink.length >= 12 && !__studio.demo().cur && !__studio.demo().planner.length)"
        await wait(a, DRAWN, 8000)
        m1 = await a.js(MARK)
        check(m1["n"] >= 3 and m1["min"] >= 11.5 and m1["max"] <= 30.5, f"origin step: the test mark lands at the origin, left side, as G-code says ({m1['min']:.1f}–{m1['max']:.1f} mm)")
        await click(a, "[data-wz=mirror]")
        check(await a.js("__studio.wizard().d.profile.mirrorX === true"), "“it's mirrored” turns X mirroring on")
        await a.js("__studio.demo().newSheet()")
        await click(a, "[data-wz=mark]")
        await wait(a, DRAWN, 8000)
        m2 = await a.js(MARK)
        check(m2["n"] >= 3 and m2["min"] >= 278 and m2["max"] <= 299, f"drawn again, the mark is on the mirrored side ({m2['min']:.1f}–{m2['max']:.1f} mm)")
        await click(a, "[data-wz=markok]")
        await click(a, "[data-wz=next]")
        await setv(a, "#wzName", "Test plotter")
        await click(a, "[data-wz=next]")
        check(await wait(a, "__studio.machines().length === 1 && !__studio.wizard()", 5000), "wizard: saved, closed")
        rec = await a.js("__studio.machines()[0]")
        check(rec["name"] == "Test plotter" and rec["via"] == "demo" and rec["profile"]["down"] == 30 and rec["profile"]["mirrorX"] is True and rec["ready"], f"the machine keeps what the wizard set up")
        check(await a.js("__studio.S.machine.down === 30 && __studio.S.machine.mirrorX === true"), "the design side now works with the machine's settings")
        check("Test plotter" in await a.js("document.getElementById('machList').textContent"), "the machine is in the list")
        await a.goto(base + "/studio.html")
        check(await wait(a, "__studio.booted()", 8000), "reloaded")
        check(await a.js("__studio.machines().length === 1 && __studio.S.machine.down === 30 && __studio.S.machine.mirrorX === true && __studio.activeMachine().name === 'Test plotter'"), "after a reload: the machine and its settings are still there")

        # --- a second machine: the bridge. The wizard learns the plotter and saves the settings on the bridge.
        await click(a, "#wsSeg [data-ws=machine]")
        await click(a, "[data-mc=add]")
        await click(a, "[data-wz=via][data-v=bridge]")
        await setv(a, "#wzUrl", bridge)
        await click(a, "[data-wz=next]")
        check(await wait(a, "__studio.wizard() && __studio.wizard().step === 1", 8000), "bridge: connected from another origin")
        check(await a.js("__studio.wizard().d.profile.mirrorX === false"), "a new machine starts from defaults, not from the previous machine's settings")
        await wait(a, "document.getElementById('modal').textContent.includes('GRBL 1.1h')", 8000)
        await click(a, "[data-wz=next]")
        await setv(a, "#wzN_down", 33)
        await click(a, "[data-wz=next]")
        await click(a, "[data-wz=next]")
        await setv(a, "#wzName", "Studio plotter")
        await click(a, "[data-wz=next]")
        check(await wait(a, "__studio.machines().length === 2 && !__studio.wizard()", 8000), "bridge machine added")
        check(await wait(a, f"__studio.activeMachine().via === 'bridge' && !__studio.activeMachine().dirty", 8000), "…and its settings were sent to the bridge")
        mb = P.machine.get()
        check(mb["name"] == "Studio plotter" and mb["profile"]["down"] == 33 and mb["profile"]["mirrorX"] is False, f"the bridge keeps the machine: {mb['name']}, pen down S{mb['profile']['down']}")
        check(await a.js("__studio.S.machine.down === 33 && __studio.S.machine.mirrorX === false"), "switching to it switches the design's machine settings")

        # --- another browser (a phone): connects and gets the same machine from the bridge
        c = await Browser(390, 844, mobile=True).start()
        await c.goto(f"http://{bridge}/studio")
        check(await wait(c, "__studio.booted() && __studio.server().st && __studio.server().st.connected", 10000), "second browser, opened from the bridge, connects by itself")
        check(await wait(c, "__studio.machines().length === 1 && __studio.machines()[0].name === 'Studio plotter' && __studio.S.machine.down === 33", 8000), "…and gets the machine and its settings from the bridge")
        # an edit in one browser reaches the other
        await click(a, "[data-mtab=set]")
        await setv(a, "#mf1 [data-key=down]", 36)
        check(await wait(c, "__studio.S.machine.down === 36", 10000), "a settings change in the first browser reaches the second")
        check(P.machine.get()["profile"]["down"] == 36, "…through the bridge")
        await setv(c, "#mName", "Pi plotter")
        check(await wait(a, "__studio.activeMachine().name === 'Pi plotter'", 10000) and P.machine.get()["name"] == "Pi plotter", "a rename in the second browser reaches the first, through the bridge")
        # two edits at once → the user is asked
        await a.js("(() => { const m = __studio.activeMachine(); m.dirty = true; m.rev -= 1; m.profile.down = 12; })()")
        await a.js("__studio.syncProfile(__studio.activeMachine())")
        check(await wait(a, "document.getElementById('modal').textContent.includes('Settings differ')", 5000), "concurrent edits: asks which settings to keep")
        await click(a, "#cfBridge")
        check(await wait(a, "__studio.S.machine.down === 36", 5000) and P.machine.get()["profile"]["down"] == 36, "“use the bridge's settings” keeps the bridge's value")
        # the list shows other bridges live
        await a.js("__studio.setWs('machine')")
        await click(a, "#machList [data-mc=card][data-id='" + await a.js("__studio.machines()[0].id") + "']")
        check(await wait(a, "document.getElementById('machList').textContent.includes('Idle') && __studio.machines().filter(m => m.via === 'bridge').length === 1", 12000),
              "a bridge that is not connected still shows its live state in the list")
        check(not a.errors and not c.errors, f"no page errors {a.errors[:2]} {c.errors[:2]}")
    finally:
        await a.close()
        if c:
            await c.close()
        srv.shutdown()
        P.disconnect()


async def hosted_build():
    """The page as GitHub Pages serves it (build_artifact.py --standalone) must still lay out for a phone."""
    print("hosted build on a phone")
    import subprocess
    import tempfile
    d = Path(tempfile.mkdtemp())
    subprocess.run([sys.executable, str(Path(__file__).parent.parent / "build_artifact.py"), str(d / "index.html"), "--standalone"], check=True, stdout=subprocess.DEVNULL)
    head = (d / "index.html").read_text()[:400]
    check(head.startswith("<!doctype html>") and 'name="viewport"' in head and 'charset="utf-8"' in head, "the standalone build has a doctype, charset and viewport")
    b = await Browser(390, 844, mobile=True).start()
    try:
        await b.goto(serve(d) + "/index.html")
        w = await b.js("({inner: innerWidth, scroll: document.documentElement.scrollWidth})")
        check(w["inner"] == 390 and w["scroll"] <= 390, f"on a 390 px phone the page is laid out at {w['inner']} px with no sideways scroll ({w['scroll']} px)")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()


async def bridge_addresses():
    print("bridge addresses, https and the ?bridge= link")
    base = serve()
    b = await Browser(1400, 900).start()
    try:
        await b.goto(base + "/studio.html")
        N = lambda addr, proto: f"(() => {{ try {{ return __studio.normBridge({addr!r}, {proto!r}); }} catch (e) {{ return 'ERR: ' + e.message; }} }})()"
        check(await b.js(N("raspberrypi.local", "http:")) == "http://raspberrypi.local:8080", "http page: a bare name gets http and the bridge's port")
        check(await b.js(N("192.168.1.5:9000", "http:")) == "http://192.168.1.5:9000", "http page: an explicit port is kept")
        check(await b.js(N("raspberrypi.tail1234.ts.net", "https:")) == "https://raspberrypi.tail1234.ts.net", "https page: a real host name gets https, no port")
        check(await b.js(N("https://pi.example.net:8443/", "https:")) == "https://pi.example.net:8443", "https page: an https address is kept")
        e = await b.js(N("192.168.1.5", "https:"))
        check(e.startswith("ERR:") and "Tailscale Serve" in e and "tailscale serve --bg 8080" in e, "https page: a plain-http bridge gets an explanation with the fix, not “open it from the bridge”")
        check(await b.js(N("localhost:8080", "https:")) == "http://localhost:8080", "https page: localhost is allowed over http")
        # the monitor links here with the bridge's address
        await b.goto(base + "/studio.html?bridge=" + "127.0.0.1:5999")
        check(await wait(b, "__studio.booted() && __studio.wizard() && __studio.wizard().d.via === 'bridge'", 8000), "?bridge= opens the wizard on the bridge option")
        check(await b.js("document.getElementById('wzUrl').value") == "http://127.0.0.1:5999", "…with that address filled in")
        check(await b.js("location.search === ''"), "…and the address bar is cleaned")
        check(not b.errors, f"no page errors {b.errors[:3]}")
    finally:
        await b.close()


async def main():
    only = sys.argv[1:]
    for name, fn in (("desktop", desktop), ("phone", phone), ("plotting", plotting), ("bridge", on_bridge), ("machines", machines_wizard), ("hosted", hosted_build), ("addresses", bridge_addresses)):
        if not only or name in only:
            await fn()
    print(f"\n{'FAILED: ' + str(len(failures)) if failures else 'all passed'}")
    sys.exit(1 if failures else 0)


asyncio.run(main())
