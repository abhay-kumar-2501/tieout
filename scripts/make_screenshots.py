"""Regenerate the README screenshots in ``docs/screenshots/``.

Needs Google Chrome and ``pip install websockets`` (a development-only helper, not a
dependency of the app). Start the app first, then run this script:

    streamlit run app/main.py --server.headless true --server.port 8791
    python scripts/make_screenshots.py

It drives Chrome over the DevTools protocol, waits for each page to finish running,
captures it at 1440 px wide and crops and downsizes each picture to a PNG under 400 KB.
Plain ``--screenshot`` with a virtual-time budget returned the loading skeleton on the
build machine, because the page is drawn over a websocket after load.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = "http://localhost:8791/"
WIDTH, SCALE = 1440, 1.5
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
#: file name -> (page, top, bottom) in CSS pixels of the full-page capture.
SHOTS = {
    "overview.png": ("", 0, 1230),
    "matching-review-queue.png": ("matching", 860, 1860),
    "risk-roadmap.png": ("risk_roadmap", 0, 1230),
}


async def capture(pages: set[str]) -> dict[str, bytes]:
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9333", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    images: dict[str, bytes] = {}
    try:
        tabs: list[dict] = []
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen("http://localhost:9333/json"))
                break
            except OSError:
                time.sleep(0.3)
        url = next(t["webSocketDebuggerUrl"] for t in tabs if t["type"] == "page")
        async with websockets.connect(url, max_size=None) as ws:
            counter = 0

            async def call(method: str, **params):
                nonlocal counter
                counter += 1
                await ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                while True:
                    reply = json.loads(await ws.recv())
                    if reply.get("id") == counter:
                        return reply.get("result")

            async def evaluate(expression: str):
                reply = await call("Runtime.evaluate", expression=expression, returnByValue=True)
                return reply["result"].get("value")

            async def size(height: int) -> None:
                await call("Emulation.setDeviceMetricsOverride", width=WIDTH, height=height,
                           deviceScaleFactor=SCALE, mobile=False)  # fmt: skip

            await size(1500)
            for page in sorted(pages):
                await call("Page.navigate", url=BASE + page)
                last = 0
                for _ in range(60):  # until the page text stops changing and nothing is running
                    await asyncio.sleep(1)
                    length = await evaluate(
                        "(()=>{const m=document.querySelector('[data-testid=stMain]');"
                        "const r=document.querySelector('[data-testid=stStatusWidget]');"
                        "return (m?m.innerText.length:0)+(r?-100000:0)})()"
                    )
                    if (length or 0) > 300 and length == last:
                        break
                    last = length or 0
                await asyncio.sleep(3)
                height = await evaluate(
                    "(()=>{const m=document.querySelector('[data-testid=stMain]');"
                    "return m?m.scrollHeight:1500})()"
                )
                await size(min(max(int(height or 1500), 900), 6000))
                await asyncio.sleep(3)
                shot = await call("Page.captureScreenshot", format="png")
                images[page] = base64.b64decode(shot["data"])
                await size(1500)
    finally:
        chrome.terminate()
    return images


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images = asyncio.run(capture({page for page, _, _ in SHOTS.values()}))
    for name, (page, top, bottom) in SHOTS.items():
        picture = Image.open(io.BytesIO(images[page])).convert("RGB")
        box = (0, int(top * SCALE), picture.width, int(bottom * SCALE))
        picture = picture.crop(box).resize((WIDTH, bottom - top), Image.LANCZOS)
        picture.save(OUT / name, optimize=True)
        print(name, (OUT / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
