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

MODEL = os.getenv("MAWID_LLM_MODEL", "claude-haiku-4-5-20251001")
API_KEY = os.getenv("ANTHROPIC_API_KEY")

SYSTEM = """أنت "مساعد موعد"، مساعد مالي شخصي لمستخدم سعودي.
- رد باللهجة السعودية البسيطة إذا كتب المستخدم بالعربي، وبالإنجليزي إذا كتب بالإنجليزي.
- لا تحسب أي رقم بنفسك أبداً. كل رقم لازم يجي من نتيجة أداة. إذا تحتاج رقم، نادِ الأداة.
- أنت "مساعد" مو "مستشار": تعطي معلومات وتنبيهات، وما توصي بقرض أو جهة تمويل أو استثمار.
- لا تشجع على الديون. إذا سأل عن شراء، اذكر خيار "تجمع أول" بنفس أهمية الخيارات الثانية.
- tightK و whenK أرقام شهور نسبية: 0 = هالشهر، 1 = الشهر الجاي، وهكذا.
- tight = اللي يبقى في أضيق شهر بعد الشراء. إذا سالب يعني ما يكفي.
- خلك مختصر: جملتين إلى ثلاث."""

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


def run_tool(con, user_id: int, name: str, args: dict) -> dict:
    if name == "get_month_summary":
        s = service.summary(con, user_id)
        return {k: s[k] for k in ("salary", "obligations_total", "safe_to_spend", "spent", "available", "alerts")}
    if name == "list_plans":
        return {"plans": [{k: p[k] for k in ("name", "amount", "day", "remaining", "total")} for p in service.plans_view(con, user_id)]}
    if name == "get_spending":
        return service.summary(con, user_id)["categories"]
    if name == "compare_scenarios":
        return service.scenarios(con, user_id, float(args["price"]))
    if name == "add_to_wishlist":
        return service.add_wish(con, user_id, args["name"], float(args["price"]), args["method"])
    if name == "check_wishlist":
        return {"items": [{"name": w["name"], "price": w["price"], "method": w["method"], "saved": w["saved"],
                           "ok": w["status"]["ok"], "whenK": w["status"]["whenK"]} for w in service.wishlist(con, user_id)]}
    if name == "get_seasonal_forecast":
        return {"available": False, "reason": "نحتاج سنة كاملة من العمليات عشان نقارن المواسم. الديمو فيه 4 شهور بس."}
    return {"error": f"unknown tool {name}"}


# short per-user memory so "طيب متى أقدر؟" works
_history: dict[int, deque] = defaultdict(lambda: deque(maxlen=10))
_last: dict[int, dict] = defaultdict(lambda: {"price": 3000.0, "method": "bnpl4", "name": "جوال"})


def chat(con, user_id: int, message: str) -> dict:
    if API_KEY:
        try:
            return _chat_llm(con, user_id, message)
        except Exception as e:   # network/LLM failure -> never break the demo
            print("LLM failed, falling back:", e)
    return _chat_rules(con, user_id, message)


def _chat_llm(con, user_id: int, message: str) -> dict:
    hist = _history[user_id]
    messages = list(hist) + [{"role": "user", "content": message}]
    used = []
    for _ in range(5):
        r = httpx.post("https://api.anthropic.com/v1/messages", timeout=30, headers={
            "x-api-key": API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": 600, "system": SYSTEM, "tools": TOOLS, "messages": messages})
        r.raise_for_status()
        data = r.json()
        messages.append({"role": "assistant", "content": data["content"]})
        calls = [b for b in data["content"] if b["type"] == "tool_use"]
        if not calls:
            reply = "".join(b.get("text", "") for b in data["content"] if b["type"] == "text").strip()
            hist.append({"role": "user", "content": message})
            hist.append({"role": "assistant", "content": reply})
            return {"reply": reply, "tools": used}
        results = []
        for c in calls:
            used.append(c["name"])
            out = run_tool(con, user_id, c["name"], c["input"])
            results.append({"type": "tool_result", "tool_use_id": c["id"], "content": json.dumps(out, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})
    return {"reply": "ما قدرت أكمل الحساب، جرب تسأل بطريقة ثانية.", "tools": used}


# ---------- fallback: rules + the same tools ----------
def _num(text: str) -> list[float]:
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", text)]


def _f(n: float) -> str:
    return f"{round(n):,}"


def _chat_rules(con, user_id: int, m: str) -> dict:
    ctx = _last[user_id]
    price = next((n for n in _num(m) if n >= 100), ctx["price"])
    method = "fin12" if re.search(r"12|تمويل", m) else "cash" if re.search(r"كاش|نقد", m) else ctx["method"]
    ctx.update(price=price, method=method)

    if re.search(r"حط|أمني|امني|ذكرني", m):
        run_tool(con, user_id, "add_to_wishlist", {"name": ctx["name"], "price": price, "method": method})
        return {"reply": "تم. بذكرك أول ما يصير مناسب 👍", "tools": ["add_to_wishlist"]}

    if re.search(r"متى|امتى", m):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})
        e = r[method]["earliest"]
        if e is None:
            return {"reply": f"بهالطريقة ما يناسب قريب. لو تجمع أول، توصل لـ {_f(price)} {E.month_label(r['save']['buyK'])}.", "tools": ["compare_scenarios"]}
        snap = service.snapshot(con, user_id)
        tight = E.evaluate(snap, method, price, e)["tight"]
        return {"reply": f"{E.month_label(e)}. وقتها يبقى لك {_f(tight)} بأضيق شهر.", "tools": ["compare_scenarios"]}

    if re.search(r"كم.*(علي|التزام|اقساط|أقساط)|وش علي", m):
        s = run_tool(con, user_id, "get_month_summary", {})
        pl = run_tool(con, user_id, "list_plans", {})["plans"]
        names = "، ".join(f"{p['name']} {_f(p['amount'])}" for p in pl if p["remaining"] != 0)
        return {"reply": f"هالشهر عليك {_f(s['obligations_total'])} ريال: {names}. وتقدر تصرف {_f(s['available'])} بعد الأساسيات.",
                "tools": ["get_month_summary", "list_plans"]}

    if re.search(r"صرف|مصاريف", m):
        c = run_tool(con, user_id, "get_spending", {})["flexible"]
        if not c:
            return {"reply": "ما صرفت شي من المصاريف المرنة هالشهر للحين.", "tools": ["get_spending"]}
        parts = "، ".join(f"{k} {_f(v)}" for k, v in c.items())
        return {"reply": f"صرفت {_f(sum(c.values()))} هالشهر: {parts}.", "tools": ["get_spending"]}

    if re.search(r"أقدر|اقدر|آخذ|اخذ|اشتري|أشتري|جوال", m):
        r = run_tool(con, user_id, "compare_scenarios", {"price": price})[method]
        lead = {"bnpl4": f"كل دفعة {_f(r['monthly'])}", "fin12": f"القسط {_f(r['monthly'])} والتكلفة الكلية {_f(r['total'])}",
                "cash": f"المبلغ كامل {_f(price)}"}[method]
        if r["ok"]:
            return {"reply": f"{lead}. بعد أقساطك ومصاريفك المعتادة يبقى لك {_f(r['tight'])} بأضيق شهر. مناسب.", "tools": ["compare_scenarios"]}
        later = ""
        if r["earliest"] is not None:
            snap = service.snapshot(con, user_id)
            later = f" لو تبدأ {E.month_label(r['earliest'])}، يبقى لك {_f(E.evaluate(snap, method, price, r['earliest'])['tight'])} بأضيق شهر."
        return {"reply": f"{lead}. {E.month_label(r['tightK'])} تصير ناقص {_f(-r['tight'])} بعد أقساطك ومصاريفك. الوضع ما يسمح الحين.{later}",
                "tools": ["compare_scenarios"]}

    return {"reply": "أقدر أجاوبك عن أقساطك، مصاريفك، أو شي تبي تشتريه. جرب: «أقدر آخذ جوال بـ 3000 على 4 دفعات؟»", "tools": []}
