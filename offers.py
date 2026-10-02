"""Sample offers only; no live provider offers or partnership is implied.

Two families are compared on the user's real cash flow:
- Installments (BNPL): small and medium purchases, each provider has a sample price cap.
- Personal finance (loans) from banks and finance companies: only from LOAN_MIN upwards (see loans.py).
The single recommendation is the option that fits soonest, then costs least, then has the lowest monthly.
"Save first" is always returned next to it.
"""
import engine as E
import loans

SAMPLE_OFFERS = (
    {"id": "tamara3", "provider": "تمارا", "label": "3 دفعات، بدون رسوم", "count": 3, "fee_pct": 0, "method": "bnpl3", "max_price": 5000},
    {"id": "tabby4", "provider": "تابي", "label": "4 دفعات، بدون رسوم", "count": 4, "fee_pct": 0, "method": "bnpl4", "max_price": 5000},
    {"id": "tamara6", "provider": "تمارا", "label": "6 شهور، رسوم 5%", "count": 6, "fee_pct": 5, "method": "bnpl6", "max_price": 10000},
)
BNPL_MIN = 100


def _bnpl(s: E.Snapshot, price: float) -> tuple[list[dict], str | None]:
    if price < BNPL_MIN:
        return [], f"التقسيط يبدأ من {BNPL_MIN} ر.س."
    rows = []
    for offer in SAMPLE_OFFERS:
        if price > offer["max_price"]:
            continue
        total = round(price * (1 + offer["fee_pct"] / 100), 2)
        pays = E.payment_schedule(offer["count"], total)
        now = E.evaluate_schedule(s, pays, total)
        earliest = next((k for k in range(E.START_HORIZON + 1)
                         if E.evaluate_schedule(s, pays, total, k)["ok"]), None)
        at_start = E.evaluate_schedule(s, pays, total, earliest) if earliest is not None else None
        rows.append({**offer, **now, "type": "bnpl", "method": offer["method"], "sample": True,
                     "extra_cost": round(total - price, 2), "total_cost": total, "earliest": earliest,
                     "earliest_label": E.month_label(earliest),
                     "start_tight": at_start["tight"] if at_start else None,
                     "start_tightK": at_start["tightK"] if at_start else None})
    reason = None if rows else "التقسيط المتاح عندنا لين 10,000 ر.س، ومبلغك أعلى."
    return rows, reason


def _rank(row: dict) -> tuple:
    return (0 if row["ok"] else 1,
            row["earliest"] if row["earliest"] is not None else float("inf"),
            row["total_cost"], row["monthly"])


def compare(s: E.Snapshot, price: float, target_months: int | None = None, debt_monthly: float = 0.0) -> dict:
    bnpl, bnpl_reason = _bnpl(s, price)
    loan = loans.compare(s, price, debt_monthly)

    candidates = [dict(r, _kind="bnpl", _id=r["id"], _months=None) for r in bnpl if r["earliest"] is not None]
    for lend in loan["lenders"]:
        if lend["feasible"]:
            o = next(x for x in lend["options"] if x["months"] == lend["default_months"])
            candidates.append(dict(o, _kind="loan", _id=lend["id"], _months=o["months"]))
    best = min(candidates, key=_rank) if candidates else None

    for row in bnpl:
        row["reason"] = (f"يبدأ {row['earliest_label']}، وتكلفته أقل من الخيارات اللي تناسب نفس الوقت."
                         if row["earliest"] is not None else "ما يناسب ميزانيتك ضمن المدة اللي حسبناها.")

    saving = E.saving_deadline(s, price, target_months)
    months = saving["months"]
    saving.update(buy_label=("الحين" if months == 0 else "بعد شهر" if months == 1 else "بعد شهرين"
                             if months == 2 else f"بعد {months} شهور" if months and months <= 10
                             else f"بعد {months} شهر" if months else "أكثر من 3 سنين"),
                  buy_date=saving["progress"][-1]["date"] if saving["buyK"] is not None and saving["progress"] else None)

    hidden = []
    if bnpl_reason:
        hidden.append({"group": "bnpl", "reason": bnpl_reason})
    if not loan["eligible"]:
        hidden.append({"group": "loans", "reason": loan["reason"]})

    return {"offers": bnpl, "loans": loan["lenders"], "dbr": loan["dbr"], "hidden": hidden,
            "best": ({"type": best["_kind"], "id": best["_id"], "months": best["_months"], "method": best["method"]}
                     if best else None),
            "best_offer_id": best["_id"] if best else None,
            "save": saving, "sample": True}
