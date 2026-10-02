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
        await self.wait(f"!document.querySelector('#p-{page} .screen-error')")
        assert await self.js("document.documentElement.scrollWidth<=window.innerWidth"), page

    async def api(self, path):
        # Evaluate in the signed-in browser; never print the session token.
        return await self.js(f"fetch({json.dumps(path)},{{headers:{{Authorization:'Bearer '+localStorage.getItem('mawid_token')}}}}).then(r=>r.json())")

    async def screenshot(self, path):
        image = await self.call("Page.captureScreenshot", {"format": "png"})
        Path(path).write_bytes(base64.b64decode(image["data"]))


async def verify(debug_url, app_url):
    with httpx.Client() as client:
        target = client.put(debug_url + "/json/new?about:blank").json()
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10_000_000) as ws:
        b = Browser(ws)
        await b.call("Runtime.enable")
        await b.call("Page.enable")
        await b.call("Page.addScriptToEvaluateOnNewDocument", {"source": "window.confirm=()=>true;"})
        await b.call("Emulation.setDeviceMetricsOverride", {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        await b.call("Page.navigate", {"url": app_url})
        await b.wait("!!document.querySelector('[data-bank=demo1]') && !document.querySelector('#ob-connect').hidden")
        await b.click("[data-bank=demo1]")
        await b.click("#btn-connect")
        await b.wait("document.querySelectorAll('[data-detected-confirm]').length===4")
        assert await b.js("document.querySelector('#btn-onboard-done').disabled")
        for idx in range(4):
            await b.js(f"document.querySelectorAll('[data-detected-confirm]')[{idx}].click()")
            await b.wait(f"document.querySelectorAll('[data-detected-confirm]')[{idx}].textContent.includes('التأكيد')")
            # Wait for re-rendered disabled, confirmed button.
            await b.wait(f"document.querySelectorAll('[data-detected-confirm]')[{idx}].disabled")
        await b.wait("!document.querySelector('#btn-onboard-done').disabled")
        await b.click("#btn-onboard-done")
        await b.wait("document.querySelector('#ov-stats').textContent.includes('7,600')")
        assert len(await b.js("[...document.querySelectorAll('.bottom-nav a')].map(a=>a.textContent.trim())")) == 5
        assert (await b.api("/api/summary"))["available"] == 180
        await b.screenshot("/tmp/mawid-phone-home.png")
        print("PASS: onboarding, four confirmations, home numbers, five RTL tabs")

        await b.route("expenses")
        await b.fill("#expense-form [name=name]", "قهوة اختبار")
        await b.fill("#expense-form [name=amount]", 20)
        await b.fill("#expense-form [name=category]", "flexible:قهوة")
        await b.js("document.querySelector('#expense-form').requestSubmit()")
        await b.wait("document.querySelector('#expense-list').textContent.includes('قهوة اختبار')")
        assert (await b.api("/api/summary"))["available"] == 160
        await b.click("[data-expense-delete]")
        await b.wait("!document.querySelector('#expense-list').textContent.includes('قهوة اختبار')")
        assert (await b.api("/api/summary"))["available"] == 180
        print("PASS: expense add/delete updates balance")

        await b.route("obligations")
        assert "7,600" in await b.js("document.querySelector('#p-obligations').textContent")
        for selector in ["[data-ob-tab=plans]", "[data-ob-tab=living]", "[data-ob-tab=all]"]:
            if await b.js(f"!!document.querySelector({json.dumps(selector)})"):
                await b.click(selector)
        form = "#plan-form"
        await b.fill(form + " [name=name]", "اشتراك اختبار")
        await b.fill(form + " [name=amount]", 50)
        await b.fill(form + " [name=day]", 10)
        await b.js(f"document.querySelector('{form}').requestSubmit()")
        await b.wait("document.querySelector('#p-obligations').textContent.includes('اشتراك اختبار')")
        assert (await b.api("/api/obligations"))["total"] == 7650
        await b.click("[data-plan-delete]")
        await b.wait("!document.querySelector('#p-obligations').textContent.includes('اشتراك اختبار')")
        print("PASS: obligation add/delete, total includes essentials without duplicate bills")

        await b.route("buy")
        await b.fill("#buy-price", 3000)
        await b.wait("document.querySelector('.offer-card.best')?.textContent.includes('تابي')")
        assert "150" in await b.js("document.querySelector('.offer-card.best').textContent")
        assert "بعد 4 شهور" in await b.js("document.querySelector('.save-card').textContent")
        assert await b.js("getComputedStyle(document.querySelector('.offer-card.best'),'::after').content.includes('الأوفر لك')")
        assert await b.js("Math.abs(document.querySelector('.offer-card.best').getBoundingClientRect().top-document.querySelector('.save-card').getBoundingClientRect().top)<2")
        await b.js("document.querySelector('#toasts').replaceChildren()")
        await b.screenshot("/tmp/mawid-phone-planner.png")
        await b.fill("#buy-name", "جوال اختبار")
        await b.click(".offer-card.best")
        await b.click("#btn-buy-wish")
        await b.wait("Number(document.querySelector('#wish-count').textContent)===2")
        await b.click("#open-wishlist")
        await b.wait("document.querySelector('#wish-list').textContent.includes('جوال اختبار')")
        assert "1,140" in await b.js("document.querySelector('#wish-list').textContent")
        await b.click("[data-wish-edit]")
        await b.fill(".wish-edit-form:not([hidden]) [name=price]", 3100)
        await b.js("document.querySelector('.wish-edit-form:not([hidden])').requestSubmit()")
        await b.wait("document.querySelector('#wish-list').textContent.includes('3,100')")
        print("PASS: best sample offer, saving schedule, wishlist badge and PATCH edit")

        await b.route("overview")
        await b.js("document.querySelector('#toasts').replaceChildren()")
        await b.click("#chat-open")
        await b.wait("document.querySelector('#chat-sheet').classList.contains('open')")
        await b.fill("#chat-input", "ضيف مصروف قهوة 20")
        await b.js("document.querySelector('#chat-form').requestSubmit()")
        await b.wait("!!document.querySelector('.confirm-action')")
        assert (await b.api("/api/summary"))["available"] == 180
        await b.click("#chat-close")
        await b.click("#chat-open")
        assert "قهوة" in await b.js("document.querySelector('#chat-messages').textContent")
        await b.click(".confirm-action")
        await b.wait("document.querySelector('#chat-messages').textContent.includes('تم التعديل')")
        await b.wait("document.querySelector('#ov-stats').textContent.includes('160')")
        await b.fill("#chat-input", "حط الجوال بالأمنيات")
        await b.js("document.querySelector('#chat-form').requestSubmit()")
        await b.wait("!!document.querySelector('.cancel-action')")
        await b.click(".cancel-action")
        await b.wait("document.querySelector('#chat-messages').textContent.includes('ألغينا')")
        await b.click("#chat-close")
        print("PASS: floating chat retains history; writes need confirm; cancel works; home refreshes")

        await b.route("account")
        assert "05XX XXX 123" in await b.js("document.querySelector('#account-profile').textContent")
        assert "79" in await b.js("document.querySelector('#tiers').textContent")
        await b.fill("#contact-form [name=name]", "مستخدم تجريبي")
        await b.fill("#contact-form [name=message]", "رسالة اختبار للواجهة")
        await b.js("document.querySelector('#contact-form').requestSubmit()")
        await b.wait("document.querySelector('#contact-form [name=message]').value===''")
        print("PASS: account, tier comparison, contact submission")
        await b.call("Emulation.setDeviceMetricsOverride", {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await b.route("overview")
        assert await b.js("document.querySelector('.phone').getBoundingClientRect().width<=430")
        assert await b.js("Math.abs(document.querySelector('.phone').getBoundingClientRect().left-(document.documentElement.clientWidth-430)/2)<2")
        await b.screenshot("/tmp/mawid-phone-desktop.png")
        assert not b.errors, b.errors
        print("PASS: desktop stays centered phone-width; no JavaScript exceptions")


def main():
    binary = shutil.which("chromium")
    if not binary:
        raise SystemExit("Chromium must already be installed to run this optional check.")
    with tempfile.TemporaryDirectory(prefix="mawid-browser-") as tmp:
        env = os.environ.copy()
        env["MAWID_DB"] = str(Path(tmp) / "isolated.db")
        env["MAWID_ENV"] = "demo"
        env.pop("ANTHROPIC_API_KEY", None)
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
                asyncio.run(verify("http://127.0.0.1:9223", "http://127.0.0.1:8008/"))
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