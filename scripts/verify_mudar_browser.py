"""Mudar phone checks against the isolated server used by verify_phone_browser."""
import asyncio
import httpx
import websockets

from verify_phone_browser import Browser


async def verify(debug_url, app_url, plans_only=False):
    with httpx.Client() as client:
        target = client.put(debug_url + "/json/new?about:blank").json()
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10_000_000) as ws:
        b = Browser(ws)
        await b.call("Runtime.enable")
        await b.call("Page.enable")
        await b.call("Page.addScriptToEvaluateOnNewDocument", {"source": "window.confirm=()=>true;"})
        await b.call("Emulation.setDeviceMetricsOverride", {
            "width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        await b.call("Page.navigate", {"url": app_url})
        await b.wait("!!document.querySelector('[data-go=signup]')")
        await b.screenshot("/tmp/mudar-welcome.png")
        await b.click("[data-go=signup]")
        await b.fill("#f-signup [name=name]", "مستخدم اختبار")
        await b.fill("#f-signup [name=phone]", "0551234567")
        await b.js("document.querySelector('#f-signup [name=terms]').checked=true;document.querySelector('#f-signup').requestSubmit()")
        await b.wait("document.querySelectorAll('#otp input').length===6")
        await b.js("document.querySelectorAll('#otp input').forEach((e,i)=>{e.value=S.demoCode[i];e.dispatchEvent(new Event('input',{bubbles:true}))})")
        await b.click("#verify")
        await b.wait("!!document.querySelector('[data-bank=demo1]')")
        await b.click("[data-bank=demo1]")
        await b.click("#approve")
        await b.wait("!!document.querySelector('[data-confirm]')")
        while await b.js("!!document.querySelector('[data-confirm]')"):
            count = await b.js("document.querySelectorAll('[data-confirm]').length")
            await b.click("[data-confirm]")
            await b.wait(f"document.querySelectorAll('[data-confirm]').length<{count}")
        await b.click("#done")
        await b.wait("!!document.querySelector('.ring-center')")
        assert (await b.api("/api/summary"))["available"] == 180
        assert (await b.api("/api/summary"))["obligations_total"] == 7600
        assert await b.js("document.querySelectorAll('#nav [data-tab]').length===5")
        print("PASS: signup, demo code, bank connection, four confirmations, initial 180/7600")

        async def route(page, selector):
            await b.js(f"location.hash='#{page}'")
            if page in ("home", "expenses", "planner", "obligations", "account"):
                await b.wait(f"document.querySelector('#nav [aria-current=page]')?.dataset.tab==='{page}'")
            await b.wait(f"!!document.querySelector({selector!r}) && !document.querySelector('#view .skeleton')")
            await asyncio.sleep(.1)

        await route("expenses", "[data-act=add-expense]")
        await b.click("[data-act=add-expense]")
        await b.wait("!!document.querySelector('#f-exp')")
        await b.fill("#f-exp [name=name]", "مصروف اختبار")
        await b.fill("#f-exp [name=amount]", 20)
        await b.fill("#f-exp [name=category]", "flexible:مطاعم ومقاهي")
        await b.js("document.querySelector('#f-exp').requestSubmit()")
        await b.wait("!document.querySelector('#f-exp') && document.querySelector('#view').textContent.includes('مصروف اختبار')")
        assert (await b.api("/api/summary"))["available"] == 160
        await b.click("[data-del-exp]")
        await b.wait("!document.querySelector('#view').textContent.includes('مصروف اختبار')")
        assert (await b.api("/api/summary"))["available"] == 180
        print("PASS: new expense categories, add/delete, balance refresh")

        await route("planner", "#pl-price")
        await b.fill("#pl-name", "جوال اختبار")
        await b.fill("#pl-price", 3000)
        await b.fill("#pl-months", 3)
        await b.wait("!!document.querySelector('[data-set-months=\"5\"]')")
        assert "1,920" in await b.js("document.querySelector('#view').textContent")
        await b.click("[data-set-months=\"5\"]")
        await b.wait("document.querySelector('#pl-months').value==='5' && !document.querySelector('[data-set-months]')")
        await b.click("[data-act=others]")
        await b.wait("document.querySelectorAll('[data-offer]').length>1")
        await b.click("[data-act=wish-offer]")
        await b.wait("location.hash==='#wishlist' && document.querySelector('#view').textContent.includes('جوال اختبار')")
        await route("wishlist", "[data-act=next-month]")
        await b.wait("document.querySelector('#view').textContent.includes('جوال اختبار')")
        print("PASS: planner recommendation/alternatives, 1920 or five deposits, wishlist")

        await route("account", "[data-act=edit-budget]")
        assert await b.js("document.querySelectorAll('#view .donut-wrap svg').length===1")
        await b.click("[data-act=edit-budget]")
        for name, value in [("essentials_pct", 86), ("personal_pct", 4), ("savings_pct", 10)]:
            await b.fill(f"#f-budget [name={name}]", value)
        await b.js("document.querySelector('#f-budget').requestSubmit()")
        await b.wait("!document.querySelector('#f-budget')")
        assert (await b.api("/api/budget"))["targets"]["personal_pct"] == 4
        await route("home", ".ring-center")
        await b.wait("document.querySelector('#view').textContent.includes('تعدّى 4%')")
        await route("account", "[data-theme-set=light]")
        await b.click("[data-theme-set=light]")
        await b.wait("document.documentElement.dataset.theme==='light'")
        await b.call("Page.reload")
        await b.wait("!!document.querySelector('[data-theme-set=dark]')")
        assert await b.js("document.documentElement.dataset.theme==='light'")
        await b.click("[data-theme-set=dark]")
        await b.screenshot("/tmp/mudar-account.png")
        print("PASS: budget chart/target legend/warnings, light-dark appearance and reload persistence")

        await route("subscriptions", "[data-plan-switch=basic]")
        await b.click("[data-plan-switch=basic]")
        await b.wait("document.querySelector('[data-plan-switch=basic]').getAttribute('aria-pressed')==='true'")
        await route("planner", "#pl-out .lock")
        await route("subscriptions", "[data-plan-switch=premium]")
        await b.click("[data-plan-switch=premium]")
        await b.wait("document.querySelector('[data-plan-switch=premium]').getAttribute('aria-pressed')==='true'")
        assert len((await b.api("/api/forecast"))["months"]) == 12
        await route("account", "[data-act=logout]")
        await b.click("[data-act=logout]")
        await b.wait("!!document.querySelector('[data-go=demo]')")
        await b.click("[data-go=demo]")
        await route("home", ".ring-center")
        assert "نورة" in await b.js("document.querySelector('#topbar').textContent")
        print("PASS: subscription switching, planner lock, Premium forecast, logout, Noura quick login")

        await route("obligations", "[data-act=pay]")
        await b.click("[data-act=pay]")
        await b.wait("!!document.querySelector('#layer input[data-pick]')")
        await b.click("#pay-go")
        await b.wait("!!document.querySelector('#bank-no')")
        await b.click("#bank-no")
        assert (await b.api("/api/payments/due"))["payable_total"] == 600
        await b.click("#pay-go")
        await b.wait("!!document.querySelector('#bank-ok')")
        await b.click("#bank-ok")
        await b.wait("document.querySelector('#layer').textContent.includes('تم السداد')")
        assert (await b.api("/api/payments/due"))["payable_total"] == 0
        assert (await b.api("/api/summary"))["available"] == 180
        await b.js("closeSheet()")
        await route("home", ".ring-center")
        await b.screenshot("/tmp/mudar-home.png")
        await b.click("#fab")
        await b.wait("!!document.querySelector('#f-chat')")
        await b.fill("#chat-in", "كم أقدر أصرف؟")
        await b.js("document.querySelector('#f-chat').requestSubmit()")
        await b.wait("document.querySelector('#msgs').textContent.includes('180')")
        await asyncio.sleep(.3)
        await b.screenshot("/tmp/mudar-chat.png")
        await b.js("closeSheet()")
        assert await b.js("document.documentElement.scrollWidth<=innerWidth")
        await b.call("Emulation.setDeviceMetricsOverride", {
            "width": 1366, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        assert await b.js("document.querySelector('.phone').getBoundingClientRect().width<=430")
        assert not b.errors, b.errors
        print("PASS: simulated payment reject/approve, no duplicate budget charge, assistant, phone/desktop layouts")


if __name__ == "__main__":
    from verify_phone_browser import main
    main()