"""Interactive browser smoke check using existing Chromium; isolated demo DB.

Run: python scripts/verify_phone_browser.py
No packages are installed, and the running app's database is never touched.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]


class Browser:
    def __init__(self, ws):
        self.ws, self.sequence = ws, 0
        self.errors = []

    async def call(self, method, params=None):
        self.sequence += 1
        ident = self.sequence
        await self.ws.send(json.dumps({"id": ident, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                detail = msg["params"]["exceptionDetails"]
                self.errors.append(detail.get("exception", {}).get("description", detail.get("text")))
            if msg.get("id") == ident:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def js(self, expression):
        result = await self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"])
        return result.get("result", {}).get("value")

    async def wait(self, expression, timeout=12):
        for _ in range(int(timeout * 10)):
            if await self.js(expression):
                return
            await asyncio.sleep(.1)
        raise AssertionError("Timed out: " + expression)

    async def click(self, selector):
        await self.js(f"document.querySelector({json.dumps(selector)}).click()")

    async def fill(self, selector, value):
        await self.js(f"""(() => {{const e=document.querySelector({json.dumps(selector)});
          e.value={json.dumps(str(value))};e.dispatchEvent(new Event('input',{{bubbles:true}}));}})()""")

    async def route(self, page):
        await self.js(f"location.hash={json.dumps('#' + page)}")
        await self.wait(f"document.querySelector('#p-{page}').classList.contains('active') && "
                        f"!document.querySelector('#p-{page} .screen-loading')")
        assert not await self.js(f"document.querySelector('#p-{page} .screen-error')?.textContent"), \
            await self.js(f"document.querySelector('#p-{page} .screen-error')?.textContent")
        assert await self.js("document.documentElement.scrollWidth<=window.innerWidth"), page

    async def api(self, path):
        # Evaluate in the signed-in browser; never print the session token.
        return await self.js(f"fetch({json.dumps(path)},{{headers:{{Authorization:'Bearer '+localStorage.getItem('mawid_token')}}}}).then(r=>r.json())")

    async def screenshot(self, path):
        image = await self.call("Page.captureScreenshot", {"format": "png"})
        Path(path).write_bytes(base64.b64decode(image["data"]))



def main():
    from verify_mudar_browser import verify
    binary = shutil.which("chromium")
    if not binary:
        raise SystemExit("Chromium must already be installed to run this optional check.")
    with tempfile.TemporaryDirectory(prefix="mawid-browser-") as tmp:
        env = os.environ.copy()
        env["MAWID_DB"] = str(Path(tmp) / "isolated.db")
        env["MAWID_ENV"] = "demo"
        # This deliberately dense browser check exceeds normal human request
        # rates. Raise ONLY the isolated test server's cap; real app unchanged.
        env["RATE_LIMIT"] = "1000"
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("MUDAR_ALLOW_ANON", None)
        with open(Path(tmp) / "server.log", "w") as log:
            server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8008"], cwd=ROOT, env=env, stdout=log, stderr=log)
            chrome = subprocess.Popen([binary, "--headless", "--no-sandbox", "--disable-gpu", "--remote-debugging-port=9223",
                                       "--remote-allow-origins=*", "--user-data-dir=" + str(Path(tmp) / "chrome"), "about:blank"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                import time
                for _ in range(80):
                    try:
                        httpx.get("http://127.0.0.1:8008/api/health", timeout=1).raise_for_status()
                        httpx.get("http://127.0.0.1:9223/json/version", timeout=1).raise_for_status()
                        break
                    except httpx.HTTPError:
                        time.sleep(.1)
                asyncio.run(verify("http://127.0.0.1:9223", "http://127.0.0.1:8008/", plans_only="--plans-only" in sys.argv))
            finally:
                for process in (chrome, server):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()