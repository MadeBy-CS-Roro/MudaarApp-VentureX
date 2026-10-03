"""
Personal finance (loans) from banks and finance companies — SAMPLE catalogue for the demo.

Real rates must come from the lenders (partnership / their published offers). The maths is real:
- Saudi personal finance is usually quoted as a FLAT annual profit rate:
    profit = amount x rate x years, monthly = (amount + profit) / months
- Admin fee: 1% of the amount, max 5,000 SAR (the usual consumer-finance cap; confirm with SAMA rules).
- APR (the real yearly cost) is solved from the cash flows: you receive (amount - fee) and pay `monthly` n times.
- Debt burden ratio (DBR): all monthly debt payments / salary. 33.33% is the usual consumer-finance limit.
"""
from __future__ import annotations

import engine as E

LENDERS = (
    {"id": "bank_a", "name": "بنك أ", "type": "bank", "flat_rate": 2.75, "tenors": (12, 24, 36, 48, 60)},
    {"id": "bank_b", "name": "بنك ب", "type": "bank", "flat_rate": 3.10, "tenors": (12, 24, 36, 48, 60)},
    {"id": "bank_c", "name": "بنك ج", "type": "bank", "flat_rate": 3.45, "tenors": (12, 24, 36, 48, 60)},
    {"id": "bank_d", "name": "بنك د", "type": "bank", "flat_rate": 3.90, "tenors": (12, 24, 36, 48, 60)},
    {"id": "fin_a", "name": "شركة تمويل أ", "type": "finance", "flat_rate": 5.50, "tenors": (12, 24, 36)},
    {"id": "fin_b", "name": "شركة تمويل ب", "type": "finance", "flat_rate": 6.90, "tenors": (6, 12, 24)},
)
LOAN_MIN = 5000
LOAN_MAX = 300000
FEE_PCT = 1.0
FEE_CAP = 5000
DBR_LIMIT = 33.33


def lender(lender_id: str) -> dict | None:
    return next((x for x in LENDERS if x["id"] == lender_id), None)


def apr(principal: float, fee: float, monthly: float, months: int) -> float:
    """Annual percentage rate from: receive (principal - fee) today, pay `monthly` for `months`."""
    net = principal - fee
    if net <= 0 or monthly * months <= net:
        return 0.0
    lo, hi = 0.0, 1.0
    for _ in range(100):
        r = (lo + hi) / 2
        pv = monthly * (1 - (1 + r) ** -months) / r
        if pv > net:
            lo = r
        else:
            hi = r
    return round(r * 12 * 100, 2)


def quote(price: float, lend: dict, months: int) -> dict:
    years = months / 12
    profit = round(price * lend["flat_rate"] / 100 * years, 2)
    total = round(price + profit, 2)
    monthly = round(total / months, 2)
    fee = round(min(price * FEE_PCT / 100, FEE_CAP), 2)
    return {"months": months, "flat_rate": lend["flat_rate"], "profit": profit, "total": total,
            "monthly": monthly, "fee": fee, "total_cost": round(total + fee, 2),
            "extra_cost": round(profit + fee, 2), "apr": apr(price, fee, monthly, months)}


def payments(q: dict) -> list[float]:
    """The admin fee is paid at the start, together with the first month."""
    pays = [q["monthly"]] * q["months"]
    pays[0] = round(pays[0] + q["fee"], 2)
    return pays


def schedule(method: str, price: float) -> tuple[list[float], float]:
    """method = 'loan:<lender_id>:<months>' (used by the wishlist and the engine)."""
    _, lender_id, months = method.split(":")
    lend = lender(lender_id)
    if not lend:
        raise ValueError("unknown lender")
    q = quote(price, lend, int(months))
    return payments(q), q["total_cost"]


def compare(s: E.Snapshot, price: float, debt_monthly: float) -> dict:
    salary = s.profile.salary or 1
    current_dbr = round(debt_monthly / salary * 100, 2)
    room = round(max(0.0, salary * DBR_LIMIT / 100 - debt_monthly), 2)
    dbr = {"current_pct": current_dbr, "limit": DBR_LIMIT, "room_monthly": room, "debt_monthly": debt_monthly}
    if price < LOAN_MIN:
        return {"eligible": False, "lenders": [], "dbr": dbr,
                "reason": f"التمويل الشخصي يبدأ عادة من {LOAN_MIN:,} ر.س، ومبلغك أقل، فما نعرضه."}
    if price > LOAN_MAX:
        return {"eligible": False, "lenders": [], "dbr": dbr,
                "reason": f"المبلغ أعلى من حد التمويل الشخصي اللي نعرضه ({LOAN_MAX:,} ر.س)."}
    rows = []
    for lend in LENDERS:
        options = []
        for months in lend["tenors"]:
            q = quote(price, lend, months)
            pays = payments(q)
            now = E.evaluate_schedule(s, pays, q["total_cost"])
            earliest = next((k for k in range(E.START_HORIZON + 1)
                             if E.evaluate_schedule(s, pays, q["total_cost"], k)["ok"]), None)
            at_start = E.evaluate_schedule(s, pays, q["total_cost"], earliest) if earliest is not None else None
            dbr_after = round((debt_monthly + q["monthly"]) / salary * 100, 2)
            options.append({**q, "ok": now["ok"], "tight": now["tight"], "earliest": earliest,
                            "earliest_label": E.month_label(earliest),
                            "start_tight": at_start["tight"] if at_start else None,
                            "dbr_after": dbr_after, "dbr_ok": dbr_after <= DBR_LIMIT,
                            "method": f"loan:{lend['id']}:{months}"})
        feasible = [o for o in options if o["dbr_ok"] and o["earliest"] is not None]
        if feasible:
            # Shortest feasible tenor at the earliest start = least profit paid.
            # Shortest (cheapest) term you can start within a month; otherwise the soonest one.
            default = min(feasible, key=lambda o: (0 if o["earliest"] <= 1 else 1, o["total_cost"], o["earliest"]))
            reason = (f"أقصر مدة تناسب ميزانيتك ({o_months(default['months'])})، "
                      f"وتدفع {default['extra_cost']:,.0f} ر.س فوق المبلغ.")
        else:
            default = max(options, key=lambda o: o["months"])
            reason = ("القسط يخلّي نسبة ديونك فوق 33% من راتبك، فغالباً ما ينقبل."
                      if not default["dbr_ok"] else "القسط أعلى من اللي يتبقى لك كل شهر.")
        rows.append({"id": lend["id"], "name": lend["name"], "type": lend["type"], "flat_rate": lend["flat_rate"],
                     "options": options, "default_months": default["months"], "feasible": bool(feasible),
                     "reason": reason, "sample": True})
    return {"eligible": True, "lenders": rows, "dbr": dbr, "reason": None}


def o_months(n: int) -> str:
    return {6: "6 شهور", 12: "سنة", 24: "سنتين", 36: "3 سنين", 48: "4 سنين", 60: "5 سنين"}.get(n, f"{n} شهر")
