"""
Glue between the database, detection, and the engine.
Every number the API or the assistant returns comes from here -> engine.py.
"""
from __future__ import annotations
import json
import uuid
from datetime import date, datetime, timedelta, timezone

import db
import detect
import engine as E
import provider
import offers

DEFAULT_BUFFER = 500.0


# ---------- loading ----------
def _txs(con, user_id: int, until: date | None = None) -> list[dict]:
    q = "SELECT date, amount, direction, merchant, description, category FROM transactions WHERE user_id=? AND source='bank'"
    args = [user_id]
    if until:
        q += " AND date<=?"
        args.append(until.isoformat())
    rows = con.execute(q + " ORDER BY date", args).fetchall()
    return [dict(r, date=date.fromisoformat(r["date"])) for r in rows]


def today(con, user_id: int) -> date:
    r = con.execute("SELECT today FROM demo_state WHERE user_id=?", (user_id,)).fetchone()
    return date.fromisoformat(r["today"]) if r else date.today()


def overrides(con, user_id: int) -> dict:
    return {r["merchant"]: r["category"] for r in con.execute(
        "SELECT merchant, category FROM category_overrides WHERE user_id=?", (user_id,))}


def plans(con, user_id: int) -> list[dict]:
    rows = con.execute("SELECT * FROM plans WHERE user_id=? ORDER BY amount DESC", (user_id,)).fetchall()
    return [dict(r, action=json.loads(r["action"]) if r["action"] else None) for r in rows]


def snapshot(con, user_id: int) -> E.Snapshot:
    t = today(con, user_id)
    txs = _txs(con, user_id, t)
    sal = detect.detect_salary(txs) or {"amount": 0, "day": 27}
    cur = E.cycle_index(t, sal["day"])
    ov = overrides(con, user_id)
    essentials = detect.essentials_average(txs, sal["day"], cur, ov)
    # Manual entries affect flexible spending only, never salary detection,
    # bank classifications, or the historical essentials average.
    manual = [
        dict(r, date=date.fromisoformat(r["date"]), direction="debit")
        for r in con.execute(
            "SELECT date, amount, merchant, description, category FROM manual_expenses "
            "WHERE user_id=? AND date<=? UNION ALL "
            "SELECT date, amount, merchant, description, category FROM transactions "
            "WHERE user_id=? AND date<=? AND source='manual' AND direction='debit'",
            (user_id, t.isoformat(), user_id, t.isoformat())
        )
    ]
    spent = 0.0
    by_cat: dict[str, float] = {}
    for x in txs + manual:
        if x["direction"] == "debit" and E.cycle_index(x["date"], sal["day"]) == cur:
            cat = x["category"] or detect.categorize(x["merchant"], x["description"], ov) or "flexible:غير مصنف"
            if cat.startswith("flexible:"):
                spent += x["amount"]
                name = cat.split(":", 1)[1]
                by_cat[name] = by_cat.get(name, 0) + x["amount"]
    ps = [E.Plan(p["id"], p["name"], p["amount"], p["day"], p["active_until"], p["total_count"]) for p in plans(con, user_id)]
    s = E.Snapshot(E.Profile(sal["amount"], sal["day"], essentials, DEFAULT_BUFFER), ps, cur, spent)
    s.extra = {"today": t, "flexible_by_category": by_cat, "essentials_by_category": _ess_breakdown(txs, sal["day"], cur, ov)}
    return s


def _ess_breakdown(txs, salary_day, cur, ov) -> dict:
    sums: dict[str, float] = {}
    for x in txs:
        c = E.cycle_index(x["date"], salary_day)
        if x["direction"] == "debit" and cur - 3 <= c < cur:
            cat = x["category"] or detect.categorize(x["merchant"], x["description"], ov) or ""
            if cat.startswith("essential:"):
                n = cat.split(":", 1)[1]
                sums[n] = sums.get(n, 0) + x["amount"] / 3
    return {k: round(v) for k, v in sums.items()}


# ---------- onboarding ----------
def connect_bank(con, user_hash: str, bank_id: str) -> dict:
    con.execute("INSERT OR IGNORE INTO users(user_hash, display_name) VALUES (?, ?)", (user_hash, "نورة"))
    user_id = con.execute("SELECT id FROM users WHERE user_hash=?", (user_hash,)).fetchone()["id"]
    # fresh start for the demo
    for table in ("transactions", "manual_expenses", "plans", "wishlist", "demo_state", "category_overrides", "pending_actions", "chat_usage"):
        con.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    con.execute("UPDATE consents SET status='revoked' WHERE user_id=?", (user_id,))

    consent_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    con.execute("INSERT INTO consents VALUES (?,?,?,?,?,?,?)",
                (consent_id, user_id, bank_id, json.dumps(provider.SCOPES), "active",
                 now.isoformat(), (now + timedelta(days=90)).isoformat()))

    txs = provider.fetch_transactions(bank_id)
    for x in txs:
        con.execute("INSERT INTO transactions(user_id,date,amount,direction,merchant,description,category) VALUES (?,?,?,?,?,?,?)",
                    (user_id, x["date"].isoformat(), x["amount"], x["direction"], x["merchant"], x["description"],
                     detect.categorize(x["merchant"], x["description"])))
    con.execute("INSERT INTO demo_state VALUES (?,?)", (user_id, provider.DEMO_TODAY.isoformat()))

    sal = detect.detect_salary(txs)
    found = detect.detect_plans(txs, sal["day"])
    for p in found:
        con.execute("INSERT INTO plans(id,user_id,name,merchant,kind,amount,day,active_until,total_count,confirmed,action) VALUES (?,?,?,?,?,?,?,?,?,0,?)",
                    (p["id"], user_id, p["name"], p["merchant"], p["kind"], p["amount"], p["day"],
                     p["active_until"], p["total_count"], json.dumps(p["action"], ensure_ascii=False)))
    con.execute("INSERT INTO wishlist(user_id,name,price,method,saved) VALUES (?,?,?,?,?)", (user_id, "عمرة", 3800, "save", 1140))
    unknown = sorted({x["merchant"] for x in txs if detect.categorize(x["merchant"], x["description"]) is None})
    return {"user_id": user_id, "consent_id": consent_id, "plans": found, "unknown_merchants": unknown,
            "expires_at": (now + timedelta(days=90)).isoformat()}


def revoke(con, user_id: int):
    con.execute("UPDATE consents SET status='revoked' WHERE user_id=?", (user_id,))
    for table in ("transactions", "manual_expenses", "plans", "demo_state", "wishlist", "category_overrides", "pending_actions", "chat_usage"):
        con.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))


def plans_view(con, user_id: int) -> list[dict]:
    s = snapshot(con, user_id)
    out = []
    for p in plans(con, user_id):
        plan = E.Plan(p["id"], p["name"], p["amount"], p["day"], p["active_until"], p["total_count"])
        out.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "amount": p["amount"], "day": p["day"],
                    "total": p["total_count"], "remaining": plan.remaining_from(s.current),
                    "confirmed": bool(p["confirmed"]), "action": p["action"],
                    "source": "manual" if p["merchant"].startswith("MANUAL:") else "bank",
                    "progress": min(100, max(0, round((p["total_count"] - (plan.remaining_from(s.current) or 0))
                                       / p["total_count"] * 100))) if p["total_count"] else None})
    return out


def confirm_plan(con, user_id: int, plan_id: str, amount: float | None, remaining: int | None) -> bool:
    row = con.execute("SELECT * FROM plans WHERE user_id=? AND id=?", (user_id, plan_id)).fetchone()
    if not row:
        return False
    cur = snapshot(con, user_id).current
    active_until = row["active_until"] if remaining is None else cur + remaining - 1
    con.execute("UPDATE plans SET confirmed=1, amount=?, active_until=? WHERE user_id=? AND id=?",
                (row["amount"] if amount is None else amount, active_until, user_id, plan_id))
    return True


# ---------- summary ----------
def summary(con, user_id: int) -> dict:
    s = snapshot(con, user_id)
    t, sd, cur = s.extra["today"], s.profile.salary_day, s.current
    next_salary = E.cycle_start(cur + 1, sd)
    safe = E.safe_to_spend(s, cur)
    items, alerts = [], []
    views = {v["id"]: v for v in plans_view(con, user_id)}
    for p in s.plans:
        if not p.active_in(cur):
            continue
        due = E.due_date_in_cycle(p.day, cur, sd)
        days = (due - t).days
        items.append({**views[p.id], "due_date": due.isoformat(), "status": "paid" if days < 0 else "upcoming",
                      "days_until": days, "before_salary": 0 <= days <= 5})
    soon = [i for i in items if i["before_salary"]]
    if soon:
        alerts.append({"type": "before_salary", "amount": sum(i["amount"] for i in soon),
                       "plans": [{"name": i["name"], "days_until": i["days_until"]} for i in soon]})
    for i in items:
        if i["remaining"] == 1:
            alerts.append({"type": "plan_ending", "name": i["name"], "frees": i["amount"]})
    if safe > 0 and s.spent_now / safe >= 0.7:
        alerts.append({"type": "spending_pace", "pct": round(s.spent_now / safe * 100), "days_to_salary": (next_salary - t).days})
    return {
        "today": t.isoformat(),
        "display_name": con.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()["display_name"],
        "salary": {"amount": s.profile.salary, "day": sd, "next_date": next_salary.isoformat(), "days_left": (next_salary - t).days},
        "formula": {"salary": s.profile.salary, "obligations": E.obligations(s, cur),
                    "essentials": s.profile.essentials, "buffer": s.profile.buffer,
                    "total_obligations": E.obligations(s, cur) + s.profile.essentials},
        "safe_to_spend": safe, "spent": s.spent_now, "available": E.available(s, 0),
        "obligations_total": E.obligations(s, cur) + s.profile.essentials,
        "plans": sorted(items, key=lambda i: i["due_date"]),
        "alerts": alerts,
        "categories": {"essentials": s.extra["essentials_by_category"], "flexible": s.extra["flexible_by_category"]},
    }


# ---------- expenses ----------
def expenses(con, user_id: int) -> list[dict]:
    """Read-only bank debits plus separately stored, deletable manual entries."""
    rows = con.execute(
        "SELECT CASE WHEN source='manual' THEN 'legacy:' ELSE 'bank:' END || id AS id, "
        "date, amount, direction, merchant, description, category, source "
        "FROM transactions WHERE user_id=? AND direction='debit' "
        "UNION ALL SELECT id, date, amount, 'debit', merchant, description, category, "
        "'manual' FROM manual_expenses WHERE user_id=? ORDER BY date DESC, id DESC",
        (user_id, user_id),
    )
    return [dict(r, deletable=r["source"] == "manual") for r in rows]


def add_expense(con, user_id: int, amount: float, merchant: str | None = None, category: str = "",
                expense_date: date | None = None, description: str = "", name: str | None = None) -> dict:
    # Preserve the phone app and confirmed assistant's name-based contract.
    # Such records retain their explicit manual source, never bank evidence.
    if name is not None:
        add_legacy_expense(con, user_id, name, amount, category)
        return {}
    t = today(con, user_id)
    expense_date = expense_date or t
    if expense_date > t:
        raise ValueError("تاريخ المصروف لا يمكن أن يكون بعد تاريخ اليوم في الحساب.")
    item_id = "manual:" + str(uuid.uuid4())
    con.execute(
        "INSERT INTO manual_expenses(id,user_id,date,amount,merchant,description,category) "
        "VALUES (?,?,?,?,?,?,?)",
        (item_id, user_id, expense_date.isoformat(), amount, merchant, description, category),
    )
    return {"id": item_id, "date": expense_date.isoformat(), "amount": amount,
            "direction": "debit", "merchant": merchant, "description": description,
            "category": category, "source": "manual", "deletable": True}


def delete_expense(con, user_id: int, item_id: str) -> bool:
    if item_id.startswith("legacy:"):
        return con.execute(
            "DELETE FROM transactions WHERE id=? AND user_id=? AND source='manual'",
            (item_id[7:], user_id),
        ).rowcount > 0
    return con.execute(
        "DELETE FROM manual_expenses WHERE id=? AND user_id=?", (item_id, user_id)
    ).rowcount > 0


# ---------- scenarios & wishlist ----------
def scenarios(con, user_id: int, price: float) -> dict:
    return E.compare(snapshot(con, user_id), price)


def wishlist(con, user_id: int) -> list[dict]:
    s = snapshot(con, user_id)
    out = []
    for r in con.execute("SELECT * FROM wishlist WHERE user_id=? ORDER BY id DESC", (user_id,)):
        item = dict(r)
        st = E.wish_status(s, item)
        label = E.month_label(st["whenK"])
        if item["method"] == "save":
            saving = E.save_first(s, item["price"], item["saved"])
            months = saving["months"]
            label = ("الحين" if months == 0 else "بعد شهر" if months == 1 else "بعد شهرين" if months == 2
                     else f"بعد {months} شهور" if months and months <= 10 else f"بعد {months} شهر" if months
                     else "أكثر من 3 سنين")
            item["saving"] = saving
        item.update(status=st, when_label=label)
        out.append(item)
    return out


def add_wish(con, user_id: int, name: str, price: float, method: str) -> dict:
    exists = con.execute("SELECT id FROM wishlist WHERE user_id=? AND name=? AND price=?", (user_id, name, price)).fetchone()
    if not exists:
        con.execute("INSERT INTO wishlist(user_id,name,price,method) VALUES (?,?,?,?)", (user_id, name, price, method))
    return {"added": not exists, "name": name, "price": price, "method": method}


def update_wish(con, user_id: int, item_id: int, price: float | None = None, method: str | None = None) -> bool:
    if price is None and method is None:
        return False
    updated = con.execute(
        "UPDATE wishlist SET price=COALESCE(?, price), method=COALESCE(?, method) "
        "WHERE id=? AND user_id=?",
        (price, method, item_id, user_id),
    )
    return updated.rowcount > 0


# ---------- demo: skip to next month ----------
def next_month(con, user_id: int) -> dict:
    before = snapshot(con, user_id)
    leftover = E.saving_amount(before, 0)
    was_ok = {w["id"]: w["status"]["ok"] for w in wishlist(con, user_id)}
    sd = before.profile.salary_day
    new_start = E.cycle_start(before.current + 1, sd)

    con.execute("INSERT INTO transactions(user_id,date,amount,direction,merchant,description,category) VALUES (?,?,?,?,?,?,?)",
                (user_id, new_start.isoformat(), before.profile.salary, "credit", "PAYROLL", "SALARY PAYROLL", "income"))
    con.execute("UPDATE demo_state SET today=? WHERE user_id=?", ((new_start + timedelta(days=1)).isoformat(), user_id))
    con.execute("UPDATE wishlist SET saved=MIN(price, saved+?) WHERE user_id=? AND method='save'", (leftover, user_id))

    events = [{"type": "salary", "amount": before.profile.salary}]
    for p in before.plans:
        if p.active_until == before.current:
            events.append({"type": "plan_end", "name": p.name, "frees": p.amount})
    after = snapshot(con, user_id)
    for w in wishlist(con, user_id):
        if w["status"]["ok"] and not was_ok.get(w["id"]) and not w["notified"]:
            con.execute("UPDATE wishlist SET notified=1 WHERE id=?", (w["id"],))
            ev = {"type": "wish_affordable", "name": w["name"], "method": w["method"]}
            if w["method"] != "save":
                ev["tight"] = E.evaluate(after, w["method"], w["price"], 0)["tight"]
            events.append(ev)
    return {"today": (new_start + timedelta(days=1)).isoformat(), "events": events}


# Ported selectively from the uploaded service, preserving current fixes.
def expense_overview(con, user_id: int) -> dict:
    s = snapshot(con, user_id)
    items = expenses(con, user_id)
    current_items = [r for r in items if date.fromisoformat(r["date"]) <= s.extra["today"]
                     and E.cycle_index(date.fromisoformat(r["date"]), s.profile.salary_day) == s.current]
    total = sum(i["amount"] for i in current_items)
    return {"items": items, "total": total, "count": len(current_items),
            "average": round(total / len(current_items), 2) if current_items else 0,
            "flexible_total": s.spent_now}


def add_legacy_expense(con, user_id: int, name: str, amount: float, category: str) -> None:
    con.execute("INSERT INTO transactions(user_id,date,amount,direction,merchant,description,category,source) "
                "VALUES (?,?,?,?,?,?,?,'manual')",
                (user_id, today(con, user_id).isoformat(), amount, "debit", name, "MANUAL", category))


def add_plan(con, user_id: int, name: str, amount: float, day: int, remaining: int | None, kind: str) -> str:
    cur = snapshot(con, user_id).current
    pid = "manual_" + uuid.uuid4().hex
    con.execute("INSERT INTO plans(id,user_id,name,merchant,kind,amount,day,active_until,total_count,confirmed,action) "
                "VALUES (?,?,?,?,?,?,?,?,?,1,NULL)",
                (pid, user_id, name, "MANUAL:" + name, kind, amount, day,
                 None if remaining is None else cur + remaining - 1, remaining))
    return pid


def delete_plan(con, user_id: int, plan_id: str) -> bool:
    return con.execute("DELETE FROM plans WHERE user_id=? AND id=?", (user_id, plan_id)).rowcount > 0


def set_category(con, user_id: int, merchant: str, category: str) -> None:
    con.execute("INSERT OR REPLACE INTO category_overrides VALUES (?,?,?)", (user_id, merchant, category))
    con.execute("UPDATE transactions SET category=? WHERE user_id=? AND merchant=?", (category, user_id, merchant))


BILL_NAMES = {"SAUDI ELECTRICITY": "فاتورة الكهرباء", "NATIONAL WATER": "فاتورة المياه",
              "STC": "باقة STC", "MOBILY": "باقة موبايلي", "ZAIN": "باقة زين"}


def obligations_view(con, user_id: int) -> dict:
    s = snapshot(con, user_id)
    current_summary = summary(con, user_id)
    items = [{**p, "type": "installment" if p["kind"] in ("bnpl", "loan") else p["kind"], "in_formula": True}
             for p in current_summary["plans"]]
    for p in plans_view(con, user_id):
        if p["remaining"] == 0:
            items.append({**p, "type": "installment", "status": "completed", "in_formula": False,
                          "due_date": None})
    seen = {}
    ov = overrides(con, user_id)
    for x in _txs(con, user_id, s.extra["today"]):
        cat = x["category"] or detect.categorize(x["merchant"], x["description"], ov) or ""
        if x["direction"] != "debit" or cat not in ("essential:فواتير", "essential:اتصالات"):
            continue
        cycle = E.cycle_index(x["date"], s.profile.salary_day)
        if cycle < s.current - 3:
            continue
        bill = seen.setdefault(x["merchant"], {"cycles": set(), "last": x, "paid_now": False})
        bill["cycles"].add(cycle)
        bill["last"] = x
        bill["paid_now"] |= cycle == s.current
    for merchant, bill in seen.items():
        if len(bill["cycles"]) < 2:
            continue
        x = bill["last"]
        due = E.due_date_in_cycle(x["date"].day, s.current, s.profile.salary_day)
        items.append({"id": "bill_" + merchant, "name": BILL_NAMES.get(merchant, merchant),
                      "type": "bill", "kind": "bill", "amount": x["amount"], "day": x["date"].day,
                      "due_date": due.isoformat(), "status": "paid" if bill["paid_now"] else
                      "late" if due < s.extra["today"] else "upcoming", "remaining": None, "total": None,
                      "action": None, "confirmed": True, "in_formula": False, "source": "bank", "progress": None})
    return {"total": current_summary["obligations_total"], "plans_total": E.obligations(s, s.current),
            "essentials_total": s.profile.essentials, "essentials_by_category": s.extra["essentials_by_category"],
            "bills_total": sum(p["amount"] for p in items if p["type"] == "bill"),
            "items": sorted(items, key=lambda p: p["due_date"] or "9999"),
            "counts": {status: sum(p["status"] == status for p in items) for status in ("paid", "upcoming", "late")}}


def offer_comparison(con, user_id: int, price: float) -> dict:
    return offers.compare(snapshot(con, user_id), price)


def consume_chat_question(con, user_id: int) -> bool:
    cycle = snapshot(con, user_id).current
    return con.execute(
        "INSERT INTO chat_usage(user_id,cycle,questions) VALUES (?,?,1) "
        "ON CONFLICT(user_id,cycle) DO UPDATE SET questions=questions+1 WHERE questions<5",
        (user_id, cycle)).rowcount > 0


def account(con, user_id: int, demo_mode: bool) -> dict:
    import os
    user = con.execute("SELECT display_name FROM users WHERE id=?", (user_id,)).fetchone()
    consent = con.execute("SELECT * FROM consents WHERE user_id=? AND status='active' "
                          "ORDER BY created_at DESC LIMIT 1", (user_id,)).fetchone()
    bank_id = consent["bank_id"] if consent else None
    names = {"demo1": "بنك تجريبي", "rajhi": "الراجحي", "snb": "الأهلي", "riyad": "بنك الرياض"}
    snap = snapshot(con, user_id)
    usage = con.execute("SELECT questions FROM chat_usage WHERE user_id=? AND cycle=?",
                        (user_id, snap.current)).fetchone()
    used = usage["questions"] if usage else 0
    return {"display_name": user["display_name"], "phone_masked": "05XX XXX 123" if demo_mode else None,
            "email": "noura@example.com" if demo_mode else None,
            "bank_id": bank_id, "bank_name": names.get(bank_id, bank_id),
            "consent_expires_at": consent["expires_at"] if consent else None,
            "salary_day": snap.profile.salary_day, "demo_mode": demo_mode,
            "subscription": {"name": "الأساسية", "price": 0, "assistant_questions": 5,
                             "questions_used": used, "questions_left": max(0, 5 - used)},
            "tiers": [
                {"id": "basic", "name": "الأساسية", "price": 0,
                 "features": ["الرئيسية والتنبيهات", "مقارنة العروض وتجمع أول", "الأمنيات", "المساعد: 5 أسئلة بالشهر"]},
                {"id": "plus", "name": "بلس", "price": 29,
                 "features": ["كل مزايا الأساسية", "أسئلة أكثر للمساعد", "تصدير التقارير"]},
                {"id": "premium", "name": "بريميوم", "price": 79,
                 "features": ["كل مزايا بلس", "حسابات العائلة", "أسئلة أكثر للمساعد"]}],
            "contact": {"email": os.getenv("MAWID_CONTACT_EMAIL"), "whatsapp": os.getenv("MAWID_CONTACT_WHATSAPP")}}
