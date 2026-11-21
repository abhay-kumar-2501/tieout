"""Regenerate the README screenshots in ``docs/screenshots/``.

Needs Google Chrome and ``pip install websockets`` (a development-only helper, not a
dependency of the app). Start the app first, then run this script:

    streamlit run app/main.py --server.headless true --server.port 8791
    python scripts/make_screenshots.py

It drives Chrome over the DevTools protocol, waits for each page to finish running,
captures it at 1440 px wide and crops and downsizes each picture to a PNG under 400 KB.
Crops run between section headings found on the page, so they follow layout changes.
Plain ``--screenshot`` with a virtual-time budget returned the loading skeleton on the
build machine, because the page is drawn over a websocket after load. Set
``TIEOUT_APP_URL`` to capture an app running on another port.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets
from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
BASE = os.environ.get("TIEOUT_APP_URL", "http://localhost:8791/").rstrip("/") + "/"
WIDTH, SCALE = 1440, 1.5
OUT = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
#: file name -> (page, first section, section after the crop). ``None`` as the first
#: section starts at the top of the page; each section is matched on the start of its text.
SHOTS = {
    "overview.png": ("", None, "How sure we are"),
    "matching-review-queue.png": (
        "matching",
        "Review the uncertain matches",
        "How accurate is the matching?",
    ),
    "risk-roadmap.png": ("risk_roadmap", None, "Concentration index before"),
}
#: Top of every section heading (and bold table title) on the page, in page pixels.
_SECTION_TOPS = (
    "(()=>{const m=document.querySelector('[data-testid=stMain]');const s=m.scrollTop;"
    "const out={};document.querySelectorAll('.to-section, [data-testid=stMarkdownContainer] "
    "strong').forEach(e=>{const k=e.innerText.trim();if(!(k in out))"
    "out[k]=e.getBoundingClientRect().top+s});return out})()"
)
MARGIN = 24  # CSS pixels kept above a section heading and cut above the next one
MAX_BYTES = 390_000  # the README test allows 400 KB a picture


async def capture(pages: set[str]) -> dict[str, tuple[bytes, dict[str, float]]]:
    profile = tempfile.mkdtemp()
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9333", f"--user-data-dir={profile}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    images: dict[str, tuple[bytes, dict[str, float]]] = {}
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
                tops = await evaluate(_SECTION_TOPS) or {}
                shot = await call("Page.captureScreenshot", format="png")
                images[page] = (base64.b64decode(shot["data"]), tops)
                await size(1500)
    finally:
        chrome.terminate()
    return images


def _section_top(tops: dict[str, float], start: str) -> int:
    """The page position of the first section heading whose text starts with ``start``."""
    for text, top in tops.items():
        if text.startswith(start):
            return int(top)
    raise SystemExit(f"No section starting {start!r} on the page; update SHOTS.")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    images = asyncio.run(capture({page for page, _, _ in SHOTS.values()}))
    for name, (page, first, after) in SHOTS.items():
        data, tops = images[page]
        top = 0 if first is None else max(_section_top(tops, first) - MARGIN, 0)
        bottom = _section_top(tops, after) - MARGIN
        picture = Image.open(io.BytesIO(data)).convert("RGB")
        box = (0, int(top * SCALE), picture.width, int(bottom * SCALE))
        picture = picture.crop(box).resize((WIDTH, bottom - top), Image.LANCZOS)
        picture.save(OUT / name, optimize=True)
        if (OUT / name).stat().st_size > MAX_BYTES:  # a flat interface survives 256 colours
            picture.quantize(colors=256, dither=Image.Dither.NONE).save(OUT / name, optimize=True)
        print(name, (OUT / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
