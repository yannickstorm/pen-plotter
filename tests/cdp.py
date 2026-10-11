"""Tiny Chrome DevTools Protocol driver for browser tests (needs google-chrome and `websockets`).

Real input (mouse, touch) goes through Input.dispatch*, so it exercises the same event path
as a person using the page: pointer capture, hit testing, default actions.
"""
import asyncio
import functools
import http.server
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request

import websockets

ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(directory=ROOT):
    """Serve `directory` over HTTP on a free port; returns the base URL."""
    port = free_port()
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Quiet, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{port}"


class Browser:
    def __init__(self, width=1400, height=900, mobile=False):
        self.width, self.height, self.mobile = width, height, mobile
        self.port = free_port()
        self.profile = tempfile.mkdtemp(prefix="cdp-")
        chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
        if not chrome:
            raise RuntimeError("google-chrome / chromium not found")
        self.proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--no-sandbox", f"--remote-debugging-port={self.port}",
                                      f"--user-data-dir={self.profile}", f"--window-size={width},{height}", "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.msg_id = 0
        self.ws = None
        self.errors = []

    async def start(self):
        for _ in range(100):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:  # noqa: BLE001 - chrome still starting
                time.sleep(0.1)
        else:
            raise RuntimeError("chrome did not start")
        self.ws = await websockets.connect(page["webSocketDebuggerUrl"], max_size=2 ** 26)
        self.events = asyncio.Queue()
        self.pending = {}
        self.reader = asyncio.create_task(self._read())
        await self.send("Runtime.enable")
        await self.send("Page.enable")
        if self.mobile:
            await self.send("Emulation.setDeviceMetricsOverride", width=self.width, height=self.height, deviceScaleFactor=2, mobile=True)
            await self.send("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        return self

    async def _read(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if "id" in m and m["id"] in self.pending:
                self.pending.pop(m["id"]).set_result(m)
            elif m.get("method") == "Runtime.exceptionThrown":
                self.errors.append(m["params"]["exceptionDetails"].get("exception", {}).get("description", str(m["params"])))
            elif m.get("method") == "Runtime.consoleAPICalled" and m["params"]["type"] == "error":
                self.errors.append(" ".join(str(a.get("value", a.get("description", ""))) for a in m["params"]["args"]))
            else:
                self.events.put_nowait(m)

    async def send(self, method, **params):
        self.msg_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.pending[self.msg_id] = fut
        await self.ws.send(json.dumps({"id": self.msg_id, "method": method, "params": params}))
        m = await asyncio.wait_for(fut, 120)
        if "error" in m:
            raise RuntimeError(f"{method}: {m['error']}")
        return m.get("result", {})

    async def goto(self, url):
        await self.send("Page.navigate", url=url)
        while True:
            m = await asyncio.wait_for(self.events.get(), 60)
            if m.get("method") == "Page.loadEventFired":
                return

    async def js(self, expr):
        """Evaluate an expression (awaited if it is a promise) and return its JSON value."""
        r = await self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", str(r["exceptionDetails"])))
        return r["result"].get("value")

    # --- real input ---------------------------------------------------
    async def mouse(self, kind, x, y, buttons=0, modifiers=0):
        await self.send("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left" if kind != "mouseMoved" or buttons else "none",
                        buttons=buttons, clickCount=1 if kind != "mouseMoved" else 0, modifiers=modifiers)

    async def mouse_drag(self, a, b, steps=12, modifiers=0):
        await self.mouse("mouseMoved", *a)
        await self.mouse("mousePressed", *a, buttons=1, modifiers=modifiers)
        for i in range(1, steps + 1):
            await self.mouse("mouseMoved", a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps, buttons=1, modifiers=modifiers)
        await self.mouse("mouseReleased", *b, buttons=0, modifiers=modifiers)

    async def touch_drag(self, a, b, steps=12):
        pt = lambda x, y: [{"x": x, "y": y, "id": 1, "radiusX": 4, "radiusY": 4, "force": 1}]
        await self.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=pt(*a))
        for i in range(1, steps + 1):
            await self.send("Input.dispatchTouchEvent", type="touchMove", touchPoints=pt(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps))
        await self.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

    async def screenshot(self, path):
        import base64
        r = await self.send("Page.captureScreenshot", format="png")
        open(path, "wb").write(base64.b64decode(r["data"]))

    async def close(self):
        try:
            await self.ws.close()
        finally:
            self.proc.terminate()
            shutil.rmtree(self.profile, ignore_errors=True)
