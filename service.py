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

DEFAULT_BUFFER = 500.0


# ---------- loading ----------
def _txs(con, user_id: int, until: date | None = None) -> list[dict]:
    q = "SELECT date, amount, direction, merchant, description, category FROM transactions WHERE user_id=?"
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
    spent = 0.0
    by_cat: dict[str, float] = {}
    for x in txs:
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
            cat = detect.categorize(x["merchant"], x["description"], ov) or ""
            if cat.startswith("essential:"):
                n = cat.split(":", 1)[1]
                sums[n] = sums.get(n, 0) + x["amount"] / 3
    return {k: round(v) for k, v in sums.items()}


# ---------- onboarding ----------
def connect_bank(con, user_hash: str, bank_id: str) -> dict:
    con.execute("INSERT OR IGNORE INTO users(user_hash, display_name) VALUES (?, ?)", (user_hash, "نورة"))
    user_id = con.execute("SELECT id FROM users WHERE user_hash=?", (user_hash,)).fetchone()["id"]
    # fresh start for the demo
    for table in ("transactions", "plans", "wishlist", "demo_state", "category_overrides"):
        con.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))

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
    for table in ("transactions", "plans", "demo_state"):
        con.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))


def plans_view(con, user_id: int) -> list[dict]:
    s = snapshot(con, user_id)
    out = []
    for p in plans(con, user_id):
        plan = E.Plan(p["id"], p["name"], p["amount"], p["day"], p["active_until"], p["total_count"])
        out.append({"id": p["id"], "name": p["name"], "kind": p["kind"], "amount": p["amount"], "day": p["day"],
                    "total": p["total_count"], "remaining": plan.remaining_from(s.current),
                    "confirmed": bool(p["confirmed"]), "action": p["action"]})
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
        "salary": {"amount": s.profile.salary, "day": sd, "next_date": next_salary.isoformat(), "days_left": (next_salary - t).days},
        "formula": {"salary": s.profile.salary, "obligations": E.obligations(s, cur),
                    "essentials": s.profile.essentials, "buffer": s.profile.buffer},
        "safe_to_spend": safe, "spent": s.spent_now, "available": E.available(s, 0),
        "obligations_total": E.obligations(s, cur),
        "plans": sorted(items, key=lambda i: i["due_date"]),
        "alerts": alerts,
        "categories": {"essentials": s.extra["essentials_by_category"], "flexible": s.extra["flexible_by_category"]},
    }


# ---------- scenarios & wishlist ----------
def scenarios(con, user_id: int, price: float) -> dict:
    return E.compare(snapshot(con, user_id), price)


def wishlist(con, user_id: int) -> list[dict]:
    s = snapshot(con, user_id)
    out = []
    for r in con.execute("SELECT * FROM wishlist WHERE user_id=? ORDER BY id DESC", (user_id,)):
        item = dict(r)
        st = E.wish_status(s, item)
        item.update(status=st, when_label=E.month_label(st["whenK"]))
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
    leftover = max(0.0, E.available(before, 0))
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
