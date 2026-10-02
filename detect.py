"""
Plan detection, categorization, and validation.
Known patterns first; the LLM is only used for merchants we cannot classify.
"""
from __future__ import annotations
import re
import statistics
from collections import Counter, defaultdict
from datetime import date

from engine import add_months, cycle_index

# ---------- categorization rules ----------
# Fixed category list. Every category belongs to one budget bucket (70/20/10 split).
CATEGORIES = {
    "essential": ["سكن وإيجار", "بقالة", "وقود", "فواتير", "اتصالات وإنترنت", "تعليم", "صحة",
                  "مواصلات", "تأمين", "التزامات مالية"],
    "flexible": ["مطاعم ومقاهي", "توصيل", "تسوق وملابس", "ترفيه", "سفر", "اشتراكات رقمية",
                 "عناية شخصية", "هدايا ومناسبات", "رياضة", "أخرى"],
}
ALL_CATEGORIES = {f"{group}:{name}" for group, names in CATEGORIES.items() for name in names}

RULES = [
    (r"NETFLIX|SHAHID|SPOTIFY|ANGHAMI|DISNEY|OSN|APPLE\.COM|ICLOUD|YOUTUBE|STARZPLAY", "subscription"),
    (r"PANDA|TAMIMI|DANUBE|OTHAIM|CARREFOUR|LULU|NESTO|BINDAWOOD", "essential:بقالة"),
    (r"ALDREES|SASCO|PETROMIN|NAFT|\bADES\b", "essential:وقود"),
    (r"ELECTRICITY|NATIONAL WATER|\bSEC\b|\bNWC\b", "essential:فواتير"),
    (r"\bSTC\b|MOBILY|ZAIN|SALAM|\bINTERNET\b", "essential:اتصالات وإنترنت"),
    (r"SCHOOL|MADARIS|UNIVERSITY|ACADEMY", "essential:تعليم"),
    (r"PHARMACY|NAHDI|ALDAWAA|HOSPITAL|CLINIC|MEDICAL", "essential:صحة"),
    (r"UBER|CAREEM|JEENY|METRO|SAPTCO|PARKING", "essential:مواصلات"),
    (r"TAWUNIYA|BUPA|INSURANCE|MEDGULF", "essential:تأمين"),
    (r"ALBAIK|HERFY|KUDU|MCDONALD|STARBUCKS|CAFE|COFFEE|RESTAURANT|BARNS|DUNKIN", "flexible:مطاعم ومقاهي"),
    (r"JAHEZ|HUNGERSTATION|MRSOOL|KEETA|TOYOU|NINJA", "flexible:توصيل"),
    (r"NOON|AMAZON|SHEIN|CENTERPOINT|NAMSHI|MAX FASHION|H&M|ZARA", "flexible:تسوق وملابس"),
    (r"CINEMA|VOX|MUVI|BOULEVARD|PLAYSTATION|STEAM", "flexible:ترفيه"),
    (r"SAUDIA|FLYNAS|FLYADEAL|BOOKING|AIRBNB|ALMOSAFER|HOTEL", "flexible:سفر"),
    (r"SALON|BARBER|SPA|SEPHORA|NICE ONE", "flexible:عناية شخصية"),
    (r"FLOWERS|GIFT|HADAYA", "flexible:هدايا ومناسبات"),
    (r"FITNESS|GYM|\bGOLD'S\b|SPORT", "flexible:رياضة"),
    (r"PAYROLL|SALARY", "income"),
    (r"TAMARA|TABBY|FINANCE|LOAN|TAMWEEL|EJAR|RENT", "installment"),
]

PROVIDERS = {
    "TAMARA": {"name": "تمارا", "kind": "bnpl", "default_total": 4,
               "action": {"kind": "url", "label": "افتح تمارا", "url": "https://tamara.co"}},
    "TABBY": {"name": "تابي", "kind": "bnpl", "default_total": 4,
              "action": {"kind": "url", "label": "افتح تابي", "url": "https://tabby.ai"}},
    "AUTO FINANCE": {"name": "تمويل السيارة", "kind": "loan", "default_total": None,
                     "action": {"kind": "url", "label": "افتح تطبيق البنك", "url": "#"}},
    "NETFLIX": {"name": "نتفليكس", "kind": "subscription", "default_total": None,
                "action": {"kind": "url", "label": "إدارة الاشتراك", "url": "https://www.netflix.com"}},
    "SHAHID": {"name": "شاهد VIP", "kind": "subscription", "default_total": None,
               "action": {"kind": "url", "label": "إدارة الاشتراك", "url": "https://shahid.mbc.net"}},
    "SPOTIFY": {"name": "سبوتيفاي", "kind": "subscription", "default_total": None,
                "action": {"kind": "url", "label": "إدارة الاشتراك", "url": "https://www.spotify.com"}},
    "DISNEY": {"name": "ديزني+", "kind": "subscription", "default_total": None,
               "action": {"kind": "url", "label": "إدارة الاشتراك", "url": "https://www.disneyplus.com"}},
    "ANGHAMI": {"name": "أنغامي", "kind": "subscription", "default_total": None,
                "action": {"kind": "url", "label": "إدارة الاشتراك", "url": "https://www.anghami.com"}},
    "EJAR": {"name": "الإيجار", "kind": "recurring", "default_total": None,
             "action": {"kind": "copy", "label": "انسخ رقم السداد", "value_from": r"SADAD (\d+)"}},
}


def categorize(merchant: str, description: str = "", overrides: dict | None = None) -> str | None:
    if overrides and merchant in overrides:
        return overrides[merchant]
    text = f"{merchant} {description}".upper()
    for pattern, cat in RULES:
        if re.search(pattern, text):
            return cat
    return None   # unknown -> LLM suggestion or user


# ---------- salary ----------
def detect_salary(txs: list[dict]) -> dict | None:
    credits = [t for t in txs if t["direction"] == "credit" and categorize(t["merchant"], t["description"]) == "income"]
    if not credits:
        return None
    day = Counter(t["date"].day for t in credits).most_common(1)[0][0]
    return {"amount": credits[-1]["amount"], "day": day}


# ---------- plans ----------
_SEQ = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")


def detect_plans(txs: list[dict], salary_day: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for t in txs:
        if t["direction"] == "debit" and categorize(t["merchant"], t["description"]) in ("installment", "subscription"):
            groups[t["merchant"].upper()].append(t)

    plans = []
    for merchant, items in groups.items():
        if len(items) < 2 and merchant not in PROVIDERS:
            continue
        items.sort(key=lambda x: x["date"])
        last = items[-1]
        meta = PROVIDERS.get(merchant, {"name": merchant.title(), "kind": "recurring", "default_total": None, "action": None})

        seq = _SEQ.search(last["description"] or "")
        if seq:
            paid, total = int(seq.group(1)), int(seq.group(2))
        elif meta["default_total"]:
            paid, total = len(items), meta["default_total"]
        else:
            paid, total = len(items), None

        if meta["kind"] == "recurring" and not seq:
            active_until = None
        elif total is None:
            active_until = None   # unknown end -> user confirms
        else:
            remaining_future = max(0, total - paid)
            active_until = cycle_index(add_months(last["date"], remaining_future), salary_day)

        action = dict(meta["action"]) if meta["action"] else None
        if action and "value_from" in action:
            m = re.search(action.pop("value_from"), last["description"] or "")
            action["value"] = m.group(1) if m else ""

        plans.append({
            "id": merchant.lower().replace(" ", "_"),
            "name": meta["name"], "merchant": merchant, "kind": meta["kind"],
            "amount": last["amount"], "day": last["date"].day,
            "active_until": active_until, "total_count": total,
            "action": action,
            "checks": validate(items, total),
        })
    return plans


# ---------- validation (step 03 "تحقق") ----------
def validate(items: list[dict], total: int | None) -> dict:
    amounts = [i["amount"] for i in items]
    dates = [i["date"] for i in items]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:])]
    amounts_equal = (max(amounts) - min(amounts)) <= 0.02 * max(amounts)
    monthly = all(27 <= g <= 33 for g in gaps) if gaps else True
    seq_ok = True
    nums = [int(m.group(1)) for i in items if (m := _SEQ.search(i["description"] or ""))]
    if len(nums) >= 2:
        seq_ok = all(b - a == 1 for a, b in zip(nums, nums[1:]))
    total_ok = total is None or len(items) <= total
    passed = sum([amounts_equal, monthly, seq_ok, total_ok])
    return {"amounts_equal": amounts_equal, "monthly_interval": monthly, "sequence_ok": seq_ok,
            "within_total": total_ok, "confidence": round(passed / 4, 2), "needs_user": passed < 4 or total is None}


# ---------- essentials average ----------
def essentials_average(txs: list[dict], salary_day: int, current: int, overrides=None, cycles: int = 3) -> float:
    per_cycle: dict[int, float] = defaultdict(float)
    for t in txs:
        if t["direction"] != "debit":
            continue
        cat = t.get("category") or categorize(t["merchant"], t["description"], overrides) or ""
        if cat.startswith("essential:"):
            per_cycle[cycle_index(t["date"], salary_day)] += t["amount"]
    complete = [per_cycle.get(current - k, 0.0) for k in range(1, cycles + 1) if (current - k) in per_cycle]
    return round(statistics.mean(complete), 2) if complete else 0.0
