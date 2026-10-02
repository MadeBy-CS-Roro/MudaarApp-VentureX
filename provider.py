"""
Fake open banking provider for the hackathon.
In production this is replaced by a licensed AIS provider (e.g. Lean or Tarabut):
same function signature, real HTTP calls, read-only scopes.

Persona: Noura. Demo "today" is 2026-10-24, salary day 27.
All numbers here are chosen so the demo story matches the pitch:
  safe to spend = 8,700 - 4,100 - 3,500 - 500 = 600, spent 420 -> 180 left.
"""
from datetime import date, timedelta

DEMO_TODAY = date(2026, 10, 24)
SCOPES = ["accounts:read", "balances:read", "transactions:read"]

_CYCLE_STARTS = [date(2026, 6, 27), date(2026, 7, 27), date(2026, 8, 27), date(2026, 9, 27)]


def fetch_transactions(bank_id: str, until: date = DEMO_TODAY) -> list[dict]:
    t: list[dict] = []

    def add(d, amount, merchant, desc, direction="debit"):
        if d <= until:
            t.append({"date": d, "amount": float(amount), "merchant": merchant,
                      "description": desc, "direction": direction})

    for i, s in enumerate(_CYCLE_STARTS):
        add(s, 8700, "PAYROLL", "SALARY PAYROLL", "credit")
        # essentials: 1,600 groceries + 700 fuel + 600 bills + 600 telecom = 3,500
        for off in (2, 9, 16, 23):
            add(s + timedelta(off), 400, "PANDA" if off % 2 else "TAMIMI MARKETS", "POS PURCHASE")
        for off in (1, 7, 13, 19, 25):
            add(s + timedelta(off), 140, "ALDREES", "POS PURCHASE")
        add(s + timedelta(5), 450, "SAUDI ELECTRICITY", "SADAD BILL")
        add(s + timedelta(6), 150, "NATIONAL WATER", "SADAD BILL")
        add(s + timedelta(8), 600, "STC", "SADAD BILL")
        # flexible spending
        if i < 3:
            add(s + timedelta(4), 180, "ALBAIK", "POS PURCHASE")
            add(s + timedelta(11), 95, "JAHEZ", "ONLINE PURCHASE")
            add(s + timedelta(15), 340, "NOON", "ONLINE PURCHASE")
            add(s + timedelta(20), 220, "HERFY", "POS PURCHASE")
        if i == 1:
            add(s + timedelta(12), 45, "MAKTABAT ALFAJR", "POS PURCHASE")   # unknown merchant -> AI / user categorizes
        if i == 3:   # current cycle: 250 + 110 + 60 = 420
            add(s + timedelta(4), 120, "ALBAIK", "POS PURCHASE")
            add(s + timedelta(12), 110, "JAHEZ", "ONLINE PURCHASE")
            add(s + timedelta(18), 60, "NOON", "ONLINE PURCHASE")
            add(s + timedelta(22), 130, "HERFY", "POS PURCHASE")

    # installments and rent
    for n, d in enumerate([date(2026, 7, 3), date(2026, 8, 3), date(2026, 9, 3), date(2026, 10, 3)], 1):
        add(d, 300, "TABBY", f"TABBY INSTALLMENT {n}/4")
    for n, d in enumerate([date(2026, 8, 25), date(2026, 9, 25)], 1):
        add(d, 600, "TAMARA", f"TAMARA INSTALLMENT {n}/4")
    for n, d in enumerate([date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)], 40):
        add(d, 1200, "AUTO FINANCE", f"AUTO FINANCE INST {n}/60")
    for d in [date(2026, 7, 10), date(2026, 8, 10), date(2026, 9, 10), date(2026, 10, 10)]:
        add(d, 2000, "EJAR", "SADAD 123456789 EJAR RENT")

    return sorted(t, key=lambda x: x["date"])


def salary_transaction(d: date) -> dict:
    return {"date": d, "amount": 8700.0, "merchant": "PAYROLL", "description": "SALARY PAYROLL", "direction": "credit"}
