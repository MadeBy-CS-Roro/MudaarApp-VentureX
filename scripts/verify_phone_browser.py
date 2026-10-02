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


async def verify(debug_url, app_url, plans_only=False):
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

        await b.route("obligations")
        assert await b.js("[...document.querySelectorAll('.plan-edit-form')].every(form => getComputedStyle(form).display === 'none')")
        await b.js("""window.planCorrections = [];
          const originalFetch = window.fetch;
          window.fetch = function(path, options) {
            if (String(path).endsWith('/confirm') && options?.method === 'POST')
              window.planCorrections.push(JSON.parse(options.body));
            return originalFetch.apply(this, arguments);
          };""")
        edit_form = '.plan-edit-form[data-plan-id="tamara"]'

        async def correct_plan(values, expected, amount, remaining):
            await b.click('[data-plan-edit="tamara"]')
            assert await b.js(f"getComputedStyle(document.querySelector('{edit_form}')).display !== 'none'")
            for field, value in values.items():
                await b.fill(edit_form + f" [name={field}]", value)
            await b.js(f"document.querySelector('{edit_form}').requestSubmit()")
            await b.wait(f"!document.querySelector('{edit_form}') || document.querySelector('{edit_form}').hidden")
            if remaining:
                assert await b.js(f"getComputedStyle(document.querySelector('{edit_form}')).display === 'none'")
            assert await b.js("window.planCorrections.at(-1)") == expected
            saved = next(p for p in (await b.api("/api/plans"))["plans"] if p["id"] == "tamara")
            assert (saved["amount"], saved["remaining"]) == (amount, remaining)
            summary = await b.api("/api/summary")
            if remaining:
                saved_summary = next(p for p in summary["plans"] if p["id"] == "tamara")
                assert (saved_summary["amount"], saved_summary["remaining"]) == (amount, remaining)
            else:
                assert "tamara" not in {p["id"] for p in summary["plans"]}
                await b.wait("document.querySelector('#ob-previous-payments').textContent.includes('تمارا')")
            if remaining:
                await b.wait(f"document.querySelector('{edit_form}').dataset.amount === '{amount}'")
                await b.wait(f"document.querySelector('{edit_form}').dataset.remaining === '{remaining}'")
            await b.wait(f"document.querySelector('#ov-stats').textContent.includes('{summary['obligations_total']:,}')")

        await correct_plan({"amount": "850"}, {"amount": 850}, 850, 2)
        await correct_plan({"remaining": "3"}, {"remaining": 3}, 850, 3)
        await correct_plan({"amount": "600", "remaining": "2"}, {"amount": 600, "remaining": 2}, 600, 2)
        await correct_plan({"amount": "٦٥٠", "remaining": ""}, {"amount": 650}, 650, 2)
        await correct_plan({"amount": "600"}, {"amount": 600}, 600, 2)
        await b.click('[data-plan-edit="tamara"]')
        count = await b.js("window.planCorrections.length")
        await b.js(f"document.querySelector('{edit_form}').requestSubmit()")
        assert await b.js("window.planCorrections.length") == count
        for field, invalid in [("amount", "-5"), ("amount", "Infinity"), ("remaining", "1.5"), ("remaining", "601")]:
            await b.fill(edit_form + f" [name={field}]", invalid)
            await b.js(f"document.querySelector('{edit_form}').requestSubmit()")
            assert await b.js("window.planCorrections.length") == count
            await b.js(f"document.querySelector('{edit_form}').reset()")
        await b.fill(edit_form + " [name=amount]", "900")
        await b.click(edit_form + " [data-plan-edit-cancel]")
        assert await b.js(f"document.querySelector('{edit_form}').hidden")
        assert await b.js(f"getComputedStyle(document.querySelector('{edit_form}')).display === 'none'")
        assert await b.js("window.planCorrections.length") == count
        await correct_plan({"amount": "", "remaining": "٠"}, {"remaining": 0}, 600, 0)
        # Restore only the isolated fixture so later incoming pay-all checks
        # still exercise the original active plan.
        await b.js("""fetch('/api/plans/tamara/confirm', {
          method: 'POST', headers: {'Content-Type':'application/json',
          Authorization:'Bearer '+localStorage.getItem('mawid_token')},
          body: JSON.stringify({remaining:2})
        }).then(r => {if (!r.ok) throw new Error('Fixture restore failed');})""")
        await b.route("overview")
        await b.route("obligations")
        print("PASS: partial plan edits omit blank/unchanged values, refresh both views, validate and cancel safely")
        if plans_only:
            await b.click('[data-plan-edit="tamara"]')
            await b.js("document.querySelector('#toasts').replaceChildren()")
            await b.screenshot("/tmp/mawid-phone-plan-editor.png")
            assert not b.errors, b.errors
            return

        await b.route("expenses")
        await b.fill("#expense-form [name=name]", "قهوة اختبار")
        await b.fill("#expense-form [name=amount]", 20)
        await b.fill("#expense-form [name=category]", "flexible:مطاعم")
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
        assert await b.js("getComputedStyle(document.querySelector('.offer-card.best'),'::after').content.includes('الأنسب لك')")
        assert await b.js("document.querySelector('.save-card').getBoundingClientRect().top>document.querySelector('.offer-card.best').getBoundingClientRect().bottom")
        assert await b.js("document.querySelector('.other-offers').hidden")
        assert "1,920" in await b.js("document.querySelector('.save-card').textContent")
        await b.click("[data-set-months]")
        await b.wait("document.querySelector('#buy-target-months').value==='5' && !document.querySelector('[data-max-target]')")
        await b.fill("#buy-target-months", 3)
        await b.wait("!!document.querySelector('[data-max-target]')")
        await b.click("[data-max-target]")
        await b.wait("document.querySelector('#buy-price').value==='1920' && !document.querySelector('[data-max-target]')")
        await b.fill("#buy-price", 3000)
        await b.wait("!!document.querySelector('[data-max-target]')")
        await b.click("[data-expand-offers]")
        assert await b.js("!document.querySelector('.other-offers').hidden")
        await b.click(".other-offers [data-method]")
        assert await b.js("document.querySelector('.other-offers .selected')!==null")
        await b.click(".offer-card.best")
        await b.click("[data-expand-offers]")
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
        assert "بلس" in await b.js("document.querySelector('#account-plan').textContent")
        await b.fill("#contact-form [name=name]", "مستخدم تجريبي")
        await b.fill("#contact-form [name=message]", "رسالة اختبار للواجهة")
        await b.js("document.querySelector('#contact-form').requestSubmit()")
        await b.wait("document.querySelector('#contact-form [name=message]').value===''")
        print("PASS: account, tier comparison, contact submission")

        assert "87%" in await b.js("document.querySelector('#budget-warnings').textContent")
        assert await b.js("document.querySelectorAll('#budget-actual-chart svg,#budget-target-chart svg').length===2")
        for name, value in [("essentials_pct", 86), ("personal_pct", 4), ("savings_pct", 10)]:
            await b.fill(f"#budget-form [name={name}]", value)
        await b.js("document.querySelector('#budget-form').requestSubmit()")
        await b.wait("document.querySelector('#budget-warnings').textContent.includes('تعدّى 4%')")
        await b.route("overview")
        await b.wait("document.querySelector('#ov-alerts').textContent.includes('تعدّى 4%')")
        await b.route("expenses")
        await b.wait("document.querySelector('#ex-summary').textContent.includes('تعدّى 4%')")
        assert await b.js("document.querySelector('#ex-summary').textContent.split('تعدّى 4%').length===2")
        await b.route("account")
        for name, value in [("essentials_pct", 70), ("personal_pct", 20), ("savings_pct", 10)]:
            await b.fill(f"#budget-form [name={name}]", value)
        await b.js("document.querySelector('#budget-form').requestSubmit()")
        await b.wait("!document.querySelector('#budget-warnings').textContent.includes('تعدّى')")
        await b.fill("#theme-choice", "dark")
        await b.js("document.querySelector('#theme-choice').dispatchEvent(new Event('change',{bubbles:true}))")
        await b.wait("document.documentElement.dataset.appearance==='dark' || document.documentElement.dataset.theme==='dark'")
        await b.js("document.querySelector('#toasts').replaceChildren();document.querySelector('#budget-actual-chart').scrollIntoView({behavior:'instant',block:'center'})")
        await asyncio.sleep(.3)
        await b.screenshot("/tmp/mawid-budget-dark.png")
        await b.call("Page.reload")
        await b.wait("document.querySelector('#p-account').classList.contains('active') && !!document.querySelector('#budget-actual-chart svg')")
        assert await b.js("document.querySelector('#theme-choice').value==='dark'")
        print("PASS: budget pies and editable targets; one personal warning on both screens; dark mode persists")

        await b.route("subscriptions")
        assert "79" in await b.js("document.querySelector('#subscription-comparison').textContent")
        await b.click("[data-demo-plan=basic]")
        await b.wait("document.querySelector('#account-plan').textContent.includes('الأساسية')")
        await b.route("buy")
        await b.fill("#buy-price", "")
        await b.wait("!!document.querySelector('#buy-scenarios .lock-card')")
        await b.route("account")
        await b.wait("!!document.querySelector('#smart-account .lock-card')")
        await b.route("obligations")
        assert await b.js("!!document.querySelector('#ob-list .lock-card')")
        await b.route("subscriptions")
        await b.click("[data-demo-plan=premium]")
        await b.wait("document.querySelector('#account-plan').textContent.includes('بريميوم')")
        await b.route("account")
        await b.wait("document.querySelectorAll('#forecast .forecast-row').length===12")
        await b.js("document.querySelector('#toasts').replaceChildren();window.scrollTo(0,0)")
        await b.screenshot("/tmp/mawid-account-dark.png")
        await b.route("overview")
        await b.click("#chat-open")
        await b.wait("document.querySelector('#chat-sheet').classList.contains('open')")
        await asyncio.sleep(.4)
        await b.screenshot("/tmp/mawid-chat-dark.png")
        await b.click("#chat-close")
        print("PASS: separate subscription comparison; Basic locks/cap; Premium 12-month forecast; dark sheets and chat")

        await b.route("subscriptions")
        await b.click("[data-demo-plan=plus]")
        await b.wait("document.querySelector('#account-plan').textContent.includes('بلس')")
        await b.route("obligations")
        await b.wait("!!document.querySelector('[data-plan-pay-all=tamara]')")
        await b.click("[data-plan-pay-all=tamara]")
        await b.wait("document.querySelector('#ob-previous-payments').textContent.includes('تمارا')")
        await b.route("wish")
        await b.click("#btn-next-month")
        await b.route("obligations")
        await b.wait("document.querySelector('#ob-previous-payments').textContent.includes('تابي')")
        assert "تابي" not in await b.js("document.querySelector('#ob-list').textContent")
        print("PASS: record Tamara pay-all; Tabby moves to previous payments next month")

        await b.route("account")
        await b.fill("#theme-choice", "system")
        await b.js("document.querySelector('#theme-choice').dispatchEvent(new Event('change',{bubbles:true}))")
        await b.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": "dark"}]})
        await b.wait("getComputedStyle(document.documentElement).colorScheme==='dark'")
        await b.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": "light"}]})
        await b.wait("getComputedStyle(document.documentElement).colorScheme==='light'")
        assert await b.js("Object.keys(localStorage).every(k=>['mawid_token','mawid_appearance'].includes(k))")
        print("PASS: system appearance follows device live; only token and appearance saved locally")
        await b.call("Emulation.setDeviceMetricsOverride", {"width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await b.route("overview")
        await b.js("document.querySelector('#toasts').replaceChildren()")
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
        # This deliberately dense browser check exceeds normal human request
        # rates. Raise ONLY the isolated test server's cap; real app unchanged.
        env["RATE_LIMIT"] = "1000"
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