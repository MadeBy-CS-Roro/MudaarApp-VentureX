"""Sample offers only; no live provider offers or partnership is implied."""
import engine as E

SAMPLE_OFFERS = (
    {"id": "tamara3", "provider": "تمارا", "label": "3 دفعات، بدون رسوم", "count": 3, "fee_pct": 0, "method": "bnpl3"},
    {"id": "tabby4", "provider": "تابي", "label": "4 دفعات، بدون رسوم", "count": 4, "fee_pct": 0, "method": "bnpl4"},
    {"id": "tamara6", "provider": "تمارا", "label": "6 شهور، رسوم 5%", "count": 6, "fee_pct": 5, "method": "bnpl6"},
    {"id": "bank12", "provider": "تمويل بنكي", "label": "12 شهر، أرباح 10%", "count": 12, "fee_pct": 10, "method": "fin12"},
)


def compare(s: E.Snapshot, price: float) -> dict:
    rows = []
    for offer in SAMPLE_OFFERS:
        total = round(price * (1 + offer["fee_pct"] / 100), 2)
        pays = E.payment_schedule(offer["count"], total)
        now = E.evaluate_schedule(s, pays, total)
        earliest = next((k for k in range(E.START_HORIZON + 1)
                         if E.evaluate_schedule(s, pays, total, k)["ok"]), None)
        at_start = E.evaluate_schedule(s, pays, total, earliest) if earliest is not None else None
        rows.append({**offer, **now, "method": offer["method"], "sample": True,
                     "extra_cost": round(total - price, 2), "earliest": earliest,
                     "earliest_label": E.month_label(earliest),
                     "start_tight": at_start["tight"] if at_start else None,
                     "start_tightK": at_start["tightK"] if at_start else None})
    best = min(rows, key=lambda r: (0 if r["ok"] else 1,
               r["earliest"] if r["earliest"] is not None else float("inf"), r["total"], r["monthly"]))
    saving = E.save_first(s, price)
    months = saving["months"]
    saving.update(buy_label=("الحين" if months == 0 else "بعد شهر" if months == 1 else "بعد شهرين"
                             if months == 2 else f"بعد {months} شهور" if months and months <= 10
                             else f"بعد {months} شهر" if months else "أكثر من 3 سنين"),
                  buy_date=saving["progress"][-1]["date"] if saving["buyK"] is not None and saving["progress"] else None)
    return {"offers": rows, "best_offer_id": best["id"], "save": saving, "sample": True}