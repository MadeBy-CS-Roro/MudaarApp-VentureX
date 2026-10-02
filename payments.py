"""
This month's payments: which ones the bank takes automatically, which ones the user
can pay from inside the app (simulated open banking payment initiation in the demo),
and which ones are paid outside (provider site, SADAD).
The app never holds customer money. Production returns 501 until partnerships exist.
"""
from __future__ import annotations
import re

from fastapi import HTTPException

import engine as E
import service

AUTO_PATTERN = re.compile(r"AUTO FINANCE|LOAN|DIRECT DEBIT|TAMWEEL", re.I)
IN_APP = {"TAMARA", "TABBY"}               # payable inside the app (demo)
PROVIDER_SITES = {"TAMARA": ("تمارا", "https://tamara.co"), "TABBY": ("تابي", "https://tabby.ai")}


def default_mode(merchant: str, kind: str) -> str:
    return "auto" if AUTO_PATTERN.search(merchant or "") or kind == "loan" and not merchant.startswith("MANUAL:") else "manual"


def mode_of(row) -> str:
    return row["pay_mode"] or default_mode(row["merchant"], row["kind"])


def paid_this_cycle(con, user_id: int, cycle: int) -> set[str]:
    return {r["plan_id"] for r in con.execute(
        "SELECT plan_id FROM cycle_payments WHERE user_id=? AND cycle=?", (user_id, cycle))}


def due(con, user_id: int) -> dict:
    s = service.snapshot(con, user_id)
    t, sd, cur = s.extra["today"], s.profile.salary_day, s.current
    paid = paid_this_cycle(con, user_id, cur)
    views = {v["id"]: v for v in service.plans_view(con, user_id)}
    groups = {"auto": [], "payable": [], "link_only": []}
    for row in con.execute("SELECT * FROM plans WHERE user_id=? ORDER BY day", (user_id,)):
        view = views.get(row["id"])
        if not view or view["remaining"] == 0:
            continue
        plan = E.Plan(row["id"], row["name"], row["amount"], row["day"], row["active_until"], row["total_count"])
        if not plan.active_in(cur):
            continue
        mode = mode_of(row)
        due_date = E.due_date_in_cycle(row["day"], cur, sd)
        days = (due_date - t).days
        item = {"id": row["id"], "name": row["name"], "amount": row["amount"], "day": row["day"],
                "due_date": due_date.isoformat(), "days_until": days, "pay_mode": mode, "action": view["action"]}
        if mode == "auto":
            next_due = due_date if days >= 0 else E.due_date_in_cycle(row["day"], cur + 1, sd)
            item["next_date"] = next_due.isoformat()
            groups["auto"].append(item)
            continue
        if days < 0 or row["id"] in paid:
            continue                       # already paid this month
        merchant = row["merchant"].upper()
        if merchant in PROVIDER_SITES:
            label, url = PROVIDER_SITES[merchant]
            item["pay_link"] = {"label": f"ادفع عند {label}", "url": url}
        groups["payable" if merchant in IN_APP else "link_only"].append(item)
    return {**groups, "payable_total": round(sum(i["amount"] for i in groups["payable"]), 2),
            "note": "الدفع يتم من حسابك البنكي مباشرة للجهات. مُدار ما يمسك فلوسك."}


def pay(con, user_id: int, item_ids: list[str], demo_mode: bool) -> dict:
    if not demo_mode:
        raise HTTPException(501, "الدفع يحتاج شراكة مع الجهات وترخيص.")
    if not item_ids:
        raise HTTPException(422, "اختر دفعة وحدة على الأقل.")
    current = due(con, user_id)
    payable = {i["id"]: i for i in current["payable"]}
    bad = [i for i in item_ids if i not in payable]
    if bad:
        raise HTTPException(422, "فيه دفعة ما تقدر تدفعها من هنا (تلقائية، مدفوعة، أو مو لك).")
    s = service.snapshot(con, user_id)
    paid = []
    for pid in dict.fromkeys(item_ids):
        item = payable[pid]
        con.execute("INSERT OR IGNORE INTO cycle_payments(user_id,plan_id,cycle,amount,paid_at,source) "
                    "VALUES (?,?,?,?,?,'mawid_demo_pay')",
                    (user_id, pid, s.current, item["amount"], s.extra["today"].isoformat()))
        paid.append({"id": pid, "name": item["name"], "amount": item["amount"]})
    return {"ok": True, "paid": paid, "total": round(sum(p["amount"] for p in paid), 2), "demo": True}


def set_mode(con, user_id: int, plan_id: str, mode: str) -> bool:
    return con.execute("UPDATE plans SET pay_mode=? WHERE user_id=? AND id=?", (mode, user_id, plan_id)).rowcount > 0
