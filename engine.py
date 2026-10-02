"""
Mawid engine: the ONLY place numbers are calculated.
Pure functions, no database, no LLM. Easy to unit test.

Cycle = the period from one salary day to the day before the next.
A cycle is identified by an integer index (year*12 + month of its start).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

FINANCING_PROFIT = 0.10   # illustrative only, user enters real rate in production
SAVE_HORIZON = 36
START_HORIZON = 24


# ---------- dates & cycles ----------
def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def cycle_index(d: date, salary_day: int) -> int:
    y, m = d.year, d.month
    if d.day < salary_day:
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return y * 12 + (m - 1)


def cycle_start(idx: int, salary_day: int) -> date:
    y, m = divmod(idx, 12)
    return date(y, m + 1, salary_day)


def due_date_in_cycle(day: int, idx: int, salary_day: int) -> date:
    start = cycle_start(idx, salary_day)
    return start.replace(day=day) if day >= salary_day else add_months(start, 1).replace(day=day)


# ---------- models ----------
@dataclass
class Plan:
    id: str
    name: str
    amount: float
    day: int
    active_until: Optional[int] = None   # last cycle index with a payment; None = recurring (rent)
    total_count: Optional[int] = None

    def active_in(self, idx: int) -> bool:
        return self.active_until is None or idx <= self.active_until

    def remaining_from(self, idx: int) -> Optional[int]:
        return None if self.active_until is None else max(0, self.active_until - idx + 1)


@dataclass
class Profile:
    salary: float
    salary_day: int
    essentials: float          # 3-cycle average
    buffer: float = 500


@dataclass
class Snapshot:
    profile: Profile
    plans: list[Plan]
    current: int               # current cycle index
    spent_now: float = 0.0     # flexible spending so far this cycle
    extra: dict = field(default_factory=dict)


# ---------- core formula ----------
def obligations(s: Snapshot, idx: int) -> float:
    return sum(p.amount for p in s.plans if p.active_in(idx))


def safe_to_spend(s: Snapshot, idx: int) -> float:
    """salary - obligations due - usual essentials - safety buffer"""
    p = s.profile
    return p.salary - obligations(s, idx) - p.essentials - p.buffer


def available(s: Snapshot, k: int) -> float:
    """What is left to spend k cycles from now (k=0 subtracts what was already spent)."""
    return safe_to_spend(s, s.current + k) - (s.spent_now if k == 0 else 0)


# ---------- purchase scenarios ----------
METHODS = ("cash", "bnpl4", "fin12")


def schedule(method: str, price: float) -> tuple[list[float], float]:
    if method == "cash":
        return [price], price
    if method == "bnpl4":
        return [price / 4] * 4, price
    if method == "fin12":
        total = round(price * (1 + FINANCING_PROFIT))
        return [total / 12] * 12, total
    raise ValueError(f"unknown method {method}")


def evaluate(s: Snapshot, method: str, price: float, start: int = 0) -> dict:
    pays, total = schedule(method, price)
    tight, tight_k = float("inf"), start
    for i, pay in enumerate(pays):
        left = available(s, start + i) - pay
        if left < tight:
            tight, tight_k = left, start + i
    return {"method": method, "monthly": round(pays[0], 2), "count": len(pays), "total": total,
            "tight": round(tight, 2), "tightK": tight_k, "ok": tight >= 0}


def earliest_start(s: Snapshot, method: str, price: float) -> Optional[int]:
    for start in range(START_HORIZON + 1):
        if evaluate(s, method, price, start)["ok"]:
            return start
    return None


def save_first(s: Snapshot, price: float, saved: float = 0) -> dict:
    total = saved
    for k in range(SAVE_HORIZON + 1):
        total += max(0.0, available(s, k))
        if total >= price:
            return {"buyK": k, "total": price}
    return {"buyK": None, "total": price}


def compare(s: Snapshot, price: float) -> dict:
    out = {}
    for m in METHODS:
        r = evaluate(s, m, price, 0)
        r["earliest"] = earliest_start(s, m, price)
        out[m] = r
    out["save"] = save_first(s, price)
    return out


# ---------- wishlist ----------
def wish_status(s: Snapshot, item: dict) -> dict:
    """'Affordable' rule: after buying, available stays >= 0 in every coming month
    (essentials and the safety buffer are already subtracted)."""
    if item["method"] == "save":
        r = save_first(s, item["price"], item.get("saved", 0))
        pct = min(100, round(item.get("saved", 0) / item["price"] * 100))
        return {"ok": r["buyK"] == 0, "whenK": r["buyK"], "pct": pct}
    e = earliest_start(s, item["method"], item["price"])
    return {"ok": e == 0, "whenK": e}


def month_label(k: Optional[int]) -> str:
    if k is None:
        return "بعد أكثر من سنة"
    return {0: "هالشهر", 1: "الشهر الجاي", 2: "بعد شهرين"}.get(k, f"بعد {k} شهور" if k <= 10 else f"بعد {k} شهر")
