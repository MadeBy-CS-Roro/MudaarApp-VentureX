"""
AI assistant with tool calling.
Rule: the engine calculates, the LLM only explains. The LLM never sees raw
transactions or merchant-level rows, only tool results (totals).

If ANTHROPIC_API_KEY is set, uses Claude with tools.
Otherwise (or if the call fails) falls back to a rule-based intent matcher,
so the live demo never depends on the network.
"""
from __future__ import annotations
import json
import os
import re
from collections import defaultdict, deque

import httpx

import engine as E
import service
import actions
import language

MODEL = os.getenv("MAWID_LLM_MODEL", "claude-haiku-4-5-20251001")
API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM = """أنت "مساعد مُدار"، مساعد مالي شخصي لمستخدم سعودي.
- رد باللهجة السعودية البسيطة إذا كتب المستخدم بالعربي، وبالإنجليزي إذا كتب بالإنجليزي.
- لا تحسب أي رقم بنفسك أبداً. كل رقم لازم يجي من نتيجة أداة. إذا تحتاج رقم، نادِ الأداة.
- أنت "مساعد" مو "مستشار": تعطي معلومات وتنبيهات، وما توصي بقرض أو جهة تمويل أو استثمار.
- لا تشجع على الديون. إذا سأل عن شراء، اذكر خيار "تجمع أول" بنفس أهمية الخيارات الثانية.
- tightK و whenK أرقام شهور نسبية: 0 = هالشهر، 1 = الشهر الجاي، وهكذا.
- tight = اللي يبقى في أضيق شهر بعد الشراء. إذا سالب يعني ما يكفي.
- خلك مختصر: جملتين إلى ثلاث."""
SYSTEM += """
- رد بلهجة سعودية بيضاء بسيطة ومتسقة. لا تستخدم فصحى رسمية.
- طابق العدد مع المعدود صح: دفعة وحدة، دفعتين، 3 دفعات، 17 دفعة؛ يوم واحد، يومين، 3 أيام، 30 يوم.
- خاطب المستخدم بالمفرد المذكر. استخدم هالشهر، الشهر الجاي، الحين، شهور، ر.س.
- قل "الالتزامات" مو "الأقساط".
- قبل أي تعديل، اعرض الملخص وانتظر التأكيد. أدوات الكتابة تنشئ طلب تأكيد فقط، مو تعديل فعلي.
- لا تقول إنك أضفت أو حذفت شي قبل ما المستخدم يأكد الطلب.
- عروض الجهات تجريبية للتوضيح، مو عروض حقيقية. لا توصي بجهة؛ قل الأوفر لك حسب الحسابات.
- تجمع أول: مبلغ التوفير ما يتعدى نسبة الادخار اللي حددها المستخدم أو المتاح؛ استخدم نتيجة الأداة بدون حساب من عندك."""

TOOLS = [
    {"name": "get_month_summary", "description": "Salary day, total obligations this month, safe-to-spend, spent so far, available now, alerts.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "list_plans", "description": "All installment plans: provider, amount, due day, payments remaining.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_spending", "description": "Flexible spending this month by category, and average essentials by category.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "compare_scenarios", "description": "Compare paying for an item in cash, 4 payments, 12-month financing, or saving first. Returns monthly amount, total cost, tightest month leftover (tight), which month (tightK), whether it fits now (ok), and the earliest month it fits (earliest).",
     "input_schema": {"type": "object", "properties": {"price": {"type": "number"}}, "required": ["price"]}},
    {"name": "add_to_wishlist", "description": "Add an item to the wishlist so the user gets notified when it becomes affordable.",
     "input_schema": {"type": "object", "properties": {"name": {"type": "string"}, "price": {"type": "number"},
                      "method": {"type": "string", "enum": ["cash", "bnpl4", "fin12", "save"]}}, "required": ["name", "price", "method"]}},
    {"name": "check_wishlist", "description": "Wishlist items with progress and when each becomes affordable (whenK).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_seasonal_forecast", "description": "Extra spending in seasons (Ramadan, Eid, back to school, summer) based on last year.",
     "input_schema": {"type": "object", "properties": {}}},
]
TOOLS = [tool for tool in TOOLS if tool["name"] != "add_to_wishlist"]
TOOLS.append({"name": "compare_offers", "description": "Sample provider offers, best offer by affordability then cost, and the capped save-first month-by-month plan.",
              "input_schema": {"type": "object", "properties": {"price": {"type": "number", "minimum": 1}}, "required": ["price"]}})
for _name, _model in actions.WRITE_MODELS.items():
    TOOLS.append({"name": _name, "description": f"Propose {_name}. DOES NOT WRITE financial data. Returns a pending confirmation card; user must confirm separately.",
                  "input_schema": _model.model_json_schema()})


def run_tool(con, user_id: int, name: str, args: dict) -> dict:
    if name in actions.WRITE_MODELS:
        try:
            return {"action": actions.propose(con, user_id, name, args)}
        except ValueError as exc:
            return {"error": str(exc)}
    if name == "get_month_summary":
        s = service.summary(con, user_id)
        return {k: s[k] for k in ("salary", "obligations_total", "safe_to_spend", "spent", "available", "alerts")}
    if name == "list_plans":
        return {"plans": [{k: p[k] for k in ("id", "name", "amount", "day", "remaining", "total")} for p in service.visible_plans(con, user_id)["plans"]]}
    if name == "get_spending":
        return service.summary(con, user_id)["categories"]
    if name == "compare_scenarios":
        return service.scenarios(con, user_id, float(args["price"]))
    if name == "compare_offers":
        return service.offer_comparison(con, user_id, float(args["price"]))
    if name == "check_wishlist":
        return {"items": [{"id": w["id"], "name": w["name"], "price": w["price"], "method": w["method"], "saved": w["saved"],
                           "ok": w["status"]["ok"], "whenK": w["status"]["whenK"]} for w in service.wishlist(con, user_id)]}
    if name == "get_seasonal_forecast":
        return {"available": False, "reason": "نحتاج سنة كاملة من العمليات عشان نقارن المواسم. الديمو فيه 4 شهور بس."}
    return {"error": f"unknown tool {name}"}


# short per-user memory so "طيب متى أقدر؟" works
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))
_last: dict[int, dict] = defaultdict(lambda: {"price": 3000.0, "method": "bnpl4", "name": "جوال"})


def chat(con, user_id: int, message: str, lang: str = "ar") -> dict:
    if API_KEY:
        try:
            result = _chat_llm(con, user_id, message, lang)
            result["mode"] = "llm"
            return result
        except Exception as e:   # network/LLM failure -> never break the demo
            print("LLM failed, falling back:", e)
    result = _chat_rules_en(con, user_id, message) if lang == "en" else _chat_rules(con, user_id, message)
    result["mode"] = "rules"
    result.setdefault("actions", [])
    return result


def _chat_llm(con, user_id: int, message: str, lang: str = "ar") -> dict:
    system = SYSTEM + ("\n- The app is in English: always reply in clear, simple English, and say 'commitments', not 'installments'."
                       if lang == "en" else "")
    hist = _history[user_id]
    messages = list(hist) + [{"role": "user", "content": message}]
    used, proposals = [], []
    for _ in range(5):
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=30, headers={
            "x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 600, "system": system, "tools": TOOLS, "messages": messages})
        r.raise_for_status()
        data = r.json()
        messages.append({"role": "assistant", "content": data["content"]})
        calls = [b for b in data["content"] if b["type"] == "tool_use"]
        if not calls:
            reply = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text").strip()
            hist.append({"role": "user", "content": message})
            hist.append({"role": "assistant", "content": reply})
            return {"reply": reply, "tools": used, "actions": proposals}
        results = []
        for c in calls:
            used.append(c["name"])
            out = run_tool(con, user_id, c["name"], c["input"])
            if "action" in out:
                proposals.append(out["action"])
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
    return {"reply": "I couldn't finish that, try asking another way." if lang == "en" else "ما قدرت أكمل الحساب، جرّب تسأل بطريقة ثانية.",
            "tools": used, "actions": proposals}


# ---------- fallback: rules + the same tools ----------
def _num(text: str) -> list[float]:
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return [float(x.replace(",", "")) for x in re.findall(r"\d+(?:,\d{3})*(?:\.\d+)?", text)]


def _f(n: float) -> str:
    return f"{round(n):,}"


def _chat_rules(con, user_id: int, m: str) -> dict:
    ctx = _last[user_id]
    price = next((n for n in _num(m) if n >= 100), ctx["price"])
    method = "save" if re.search(r"تجمع|أجمع|اجمع|تحوش|تحوّش|ادخ|أدخ", m) else "fin12" if re.search(r"12|تمويل", m) else "cash" if re.search(r"كاش|نقد", m) else "bnpl4" if re.search(r"4.*دفع|٤.*دفع", m) else ctx["method"]
    ctx.update(price=price, method=method)

    if re.search(r"(ضيف|أضف|اضف|سجل|سجّل).*مصروف", m):
        nums = _num(m)
        if not nums:
            return {"reply": "كم مبلغ المصروف؟ اكتب مثلاً: ضيف مصروف قهوة 20.", "tools": []}
        name = re.split(r"مصروف\s*", m, maxsplit=1)[-1]
        name = re.sub(r"[\d٠-٩,\.]+.*$", "", name).strip() or "مصروف"
        category = "flexible:مطاعم ومقاهي" if re.search(r"قهوة|كوفي|مطعم|غدا|عشا|فطور", name) else "flexible:أخرى"
        out = run_tool(con, user_id, "add_expense", {"name": name, "amount": nums[-1], "category": category})
        return _proposal_reply(out, "add_expense")

    if re.search(r"حط|أمني|امني|ذكرني", m):
        name_match = re.search(r"(?:حط|ضيف|أضف)\s+(.+?)(?:\s+ب|بال|في)?(?:الأمنيات|الامنيات|أمنيات|امنيات)", m)
        name = name_match.group(1).strip() if name_match else ctx["name"]
        if "جوال" in m:
            name = "جوال"
        ctx["name"] = name
        out = run_tool(con, user_id, "add_to_wishlist", {"name": name, "price": price, "method": method})
        return _proposal_reply(out, "add_to_wishlist")

    if method == "save" and re.search(r"تجمع|أجمع|اجمع|تحوش|تحوّش|ادخ|أدخ|متى", m):
        saving = run_tool(con, user_id, "compare_offers", {"price": price})["save"]
        pct = service.snapshot(con, user_id).profile.savings_pct
        return {"reply": f"تقدر تحوّش { _f(saving['monthly'])} ر.س هالشهر، وما نتعدى {_f(pct)}% من راتبك بأي شهر. توصل للمبلغ {saving['buy_label']}.",
                "tools": ["compare_offers"]}

    if re.search(r"متى|امتى", m):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})
        e = r[method]["earliest"]
        if e is None:
            return {"reply": f"بهالطريقة ما يناسب قريب. لو تجمع أول، توصل لـ {_f(price)} {E.month_label(r['save']['buyK'])}.", "tools": ["compare_scenarios"]}
        snap = service.snapshot(con, user_id)
        tight = E.evaluate(snap, method, price, e)["tight"]
        return {"reply": f"{E.month_label(e)}. وقتها يبقى لك {_f(tight)} ر.س في أضيق شهر.", "tools": ["compare_scenarios"]}

    if re.search(r"كم.*(علي|التزام|اقساط|أقساط)|وش علي", m):
        s = run_tool(con, user_id, "get_month_summary", {})
        pl = run_tool(con, user_id, "list_plans", {})["plans"]
        names = "، ".join(f"{p['name']} {_f(p['amount'])}" for p in pl if p["remaining"] != 0)
        return {"reply": f"التزاماتك هالشهر مع المعيشة {_f(s['obligations_total'])} ر.س. الالتزامات والإيجار: {names}. وتقدر تصرف {_f(s['available'])} ر.س الحين.",
                "tools": ["get_month_summary", "list_plans"]}

    if re.search(r"كم.*(?:أقدر|اقدر|تقدر).*صرف|المتاح|باقي لي|باقيلي", m):
        s = run_tool(con, user_id, "get_month_summary", {})
        return {"reply": f"تقدر تصرف {_f(s['available'])} ر.س الحين، بعد التزاماتك ومصاريفك وهامش الأمان.",
                "tools": ["get_month_summary"]}

    if re.search(r"صرف|مصاريف", m):
        c = run_tool(con, user_id, "get_spending", {})["flexible"]
        if not c:
            return {"reply": "ما صرفت شي من المصاريف المرنة هالشهر للحين.", "tools": ["get_spending"]}
        parts = "، ".join(f"{k} {_f(v)}" for k, v in c.items())
        return {"reply": f"صرفت {_f(sum(c.values()))} ر.س هالشهر: {parts}.", "tools": ["get_spending"]}

    if re.search(r"أقدر|اقدر|آخذ|اخذ|اشتري|أشتري|جوال", m):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})[method]
        lead = {"bnpl4": f"كل دفعة {_f(r['monthly'])}", "fin12": f"الدفعة الشهرية {_f(r['monthly'])} والتكلفة الكلية {_f(r['total'])}",
                "cash": f"المبلغ كامل {_f(price)}"}[method]
        if r["ok"]:
            return {"reply": f"{lead}. بعد التزاماتك ومصاريفك المعتادة يبقى لك {_f(r['tight'])} ر.س في أضيق شهر. مناسب.", "tools": ["compare_scenarios"]}
        later = ""
        if r["earliest"] is not None:
            snap = service.snapshot(con, user_id)
            later = f" لو تبدأ {E.month_label(r['earliest'])}، يبقى لك {_f(E.evaluate(snap, method, price, r['earliest'])['tight'])} ر.س في أضيق شهر."
        return {"reply": f"{lead}. {E.month_label(r['tightK'])} تصير ناقص {_f(-r['tight'])} ر.س بعد التزاماتك ومصاريفك. ما يكفيك الحين.{later}",
                "tools": ["compare_scenarios"]}

    return {"reply": "أقدر أجاوبك عن التزاماتك، مصاريفك، أو شي تبي تشتريه. جرب: «أقدر آخذ جوال بـ 3000 على 4 دفعات؟»", "tools": []}


def _proposal_reply(out: dict, tool: str) -> dict:
    action = out.get("action")
    return {"reply": "راجع الطلب وأكّد إذا يناسبك. ما تغيّر شي للحين." if action else out["error"],
            "tools": [tool], "actions": [action] if action else []}


# ---------- English fallback (same tools, English wording) ----------
def _en_month(k):
    if k is None:
        return "in more than a year"
    return {0: "this month", 1: "next month"}.get(k, f"in {k} months")


def _chat_rules_en(con, user_id: int, m: str) -> dict:
    ctx = _last[user_id]
    low = m.lower()
    price = next((n for n in _num(m) if n >= 100), ctx["price"])
    method = ("save" if re.search(r"save|saving", low) else "fin12" if re.search(r"\b12\b|financ|loan", low)
              else "cash" if "cash" in low else "bnpl4" if re.search(r"4 (payment|install)", low) else ctx["method"])
    ctx.update(price=price, method=method)

    if re.search(r"(add|log|record).*(expense|spent)", low):
        nums = _num(m)
        if not nums:
            return {"reply": "How much was it? For example: add a coffee expense 20.", "tools": []}
        before = re.search(r"(?i)(?:add|log|record)\s+(?:an?\s+)?(.+?)\s+expense", m)
        after = re.search(r"(?i)expense\s+(?:for|of|on)?\s*([^\d]+)", m)
        name = (before.group(1) if before else after.group(1) if after else "").strip()
        name = re.sub(r"[\d,\.]+.*$", "", name).strip() or "Expense"
        category = "flexible:مطاعم ومقاهي" if re.search(r"coffee|cafe|lunch|dinner|breakfast|restaurant", low) else "flexible:أخرى"
        out = run_tool(con, user_id, "add_expense", {"name": name.title(), "amount": nums[-1], "category": category})
        return _proposal_reply_en(out, "add_expense")

    if re.search(r"wish ?list|remind me", low):
        name = "Phone" if "phone" in low else ctx["name"] if not re.search("[\u0600-\u06FF]", ctx["name"]) else "Phone"
        ctx["name"] = name
        out = run_tool(con, user_id, "add_to_wishlist", {"name": name, "price": price, "method": method})
        return _proposal_reply_en(out, "add_to_wishlist")

    if method == "save":
        saving = run_tool(con, user_id, "compare_offers", {"price": price})["save"]
        pct = service.snapshot(con, user_id).profile.savings_pct
        months = saving["buyK"]
        return {"reply": f"You can save {_f(saving['monthly'])} SAR this month, never more than {_f(pct)}% of your salary in any month. "
                         f"You'll have {_f(price)} SAR {_en_month(months)}.", "tools": ["compare_offers"]}

    if re.search(r"\bwhen\b", low):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})
        e = r[method]["earliest"]
        if e is None:
            return {"reply": f"That way it won't fit soon. If you save first, you'll have {_f(price)} SAR {_en_month(r['save']['buyK'])}.",
                    "tools": ["compare_scenarios"]}
        tight = E.evaluate(service.snapshot(con, user_id), method, price, e)["tight"]
        return {"reply": f"{_en_month(e).capitalize()}. You'd still keep {_f(tight)} SAR in your tightest month.", "tools": ["compare_scenarios"]}

    if re.search(r"owe|this month|commitment|due", low):
        s = run_tool(con, user_id, "get_month_summary", {})
        return {"reply": f"Your commitments this month, including living costs, are {_f(s['obligations_total'])} SAR. "
                         f"You can still spend {_f(s['available'])} SAR now.", "tools": ["get_month_summary"]}

    if re.search(r"how much.*(?:can|could).*(?:spend|afford)|available|left to spend", low):
        s = run_tool(con, user_id, "get_month_summary", {})
        return {"reply": f"You can spend {_f(s['available'])} SAR now, after your commitments, spending and safety buffer.",
                "tools": ["get_month_summary"]}

    if re.search(r"spend|spent|spending", low):
        c = run_tool(con, user_id, "get_spending", {})["flexible"]
        if not c:
            return {"reply": "No personal spending this month yet.", "tools": ["get_spending"]}
        return {"reply": f"You've spent {_f(sum(c.values()))} SAR on personal things this month.", "tools": ["get_spending"]}

    if re.search(r"afford|can i|buy|phone|get a", low):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})[method]
        lead = {"bnpl4": f"Each payment is {_f(r['monthly'])} SAR", "fin12": f"The monthly payment is {_f(r['monthly'])} SAR, {_f(r['total'])} SAR in total",
                "cash": f"The full amount is {_f(price)} SAR", "save": f"Saving up for {_f(price)} SAR"}.get(method, "")
        if r["ok"]:
            return {"reply": f"{lead}. After your commitments and usual spending you'd keep {_f(r['tight'])} SAR in your tightest month. It fits.",
                    "tools": ["compare_scenarios"]}
        later = ""
        if r["earliest"] is not None:
            snap = service.snapshot(con, user_id)
            later = f" If you start {_en_month(r['earliest'])}, you'd keep {_f(E.evaluate(snap, method, price, r['earliest'])['tight'])} SAR in your tightest month."
        return {"reply": f"{lead}. {_en_month(r['tightK']).capitalize()} you'd be {_f(-r['tight'])} SAR short after your commitments. Not yet.{later}",
                "tools": ["compare_scenarios"]}

    return {"reply": "I can answer questions about your commitments, your spending, or something you want to buy. Try: “Can I get a 3000 phone in 4 payments?”",
            "tools": []}


def _proposal_reply_en(out: dict, tool: str) -> dict:
    action = out.get("action")
    return {"reply": "Check the request and confirm if it's right. Nothing has changed yet." if action else out.get("error", "Something went wrong."),
            "tools": [tool], "actions": [action] if action else []}
