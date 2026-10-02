"""Several banks, subscriptions with renewal reminders, loans comparison."""
import pytest

from test_mawid import client  # noqa: F401  (fixture: Noura with bank demo1)
import loans


def test_second_bank_adds_subscriptions_and_tags_expenses(client):
    r = client.post("/api/banks", json={"bank_id": "demo2"})
    assert r.status_code == 200
    assert {p["id"] for p in r.json()["plans"]} == {"netflix", "shahid", "spotify"}
    assert [b["bank_id"] for b in r.json()["banks"]] == ["demo1", "demo2"]
    assert client.post("/api/banks", json={"bank_id": "demo2"}).status_code == 409

    s = client.get("/api/summary").json()
    assert s["obligations_total"] == 7700 and s["safe_to_spend"] == 500 and s["available"] == 62
    renew = [a for a in s["alerts"] if a["type"] == "subscription_renewal"]
    assert renew and renew[0]["name"] == "نتفليكس" and renew[0]["days_until"] == 2
    before = next(a for a in s["alerts"] if a["type"] == "before_salary")
    assert [p["name"] for p in before["plans"]] == ["تمارا"]   # subscriptions have their own reminder

    items = client.get("/api/expenses").json()["items"]
    barns = next(i for i in items if i["merchant"] == "BARNS" and i["date"] == "2026-10-20")
    assert barns["bank_name"] == "بنك تجريبي ب"
    assert next(i for i in items if i["merchant"] == "PANDA")["bank_name"] == "بنك تجريبي أ"


def test_subscription_reminder_toggle_and_cancel(client):
    client.post("/api/banks", json={"bank_id": "demo2"})
    client.patch("/api/plans/netflix", json={"remind": False})
    assert not any(a["type"] == "subscription_renewal" for a in client.get("/api/summary").json()["alerts"])
    out = client.post("/api/plans/netflix/cancelled").json()
    assert out["charged_this_month"] is False and out["saves"] == 55
    assert client.get("/api/summary").json()["safe_to_spend"] == 555
    prev = client.get("/api/obligations").json()["previous_payments"]
    assert any(p["id"] == "netflix" and p["status"] == "cancelled" for p in prev)
    assert client.post("/api/plans/tamara/cancelled").status_code == 422


def test_remove_one_bank_keeps_the_rest(client):
    client.post("/api/banks", json={"bank_id": "demo2"})
    r = client.delete("/api/banks/demo2").json()
    assert r["last_bank"] is False and [b["bank_id"] for b in r["banks"]] == ["demo1"]
    s = client.get("/api/summary").json()
    assert s["safe_to_spend"] == 600 and s["available"] == 180
    assert not any(p["id"] == "netflix" for p in client.get("/api/plans").json()["plans"])


def test_small_purchase_hides_loans(client):
    r = client.post("/api/offers", json={"price": 500}).json()
    assert r["loans"] == [] and any(h["group"] == "loans" for h in r["hidden"])
    assert r["best"]["type"] == "bnpl"


def test_large_purchase_compares_loans_with_real_maths(client):
    r = client.post("/api/offers", json={"price": 15000}).json()
    assert r["offers"] == [] and any(h["group"] == "bnpl" for h in r["hidden"])
    assert r["best"] == {"type": "loan", "id": "bank_a", "months": 24, "method": "loan:bank_a:24"}
    bank_a = next(l for l in r["loans"] if l["id"] == "bank_a")
    o24 = next(o for o in bank_a["options"] if o["months"] == 24)
    assert o24["profit"] == 825 and o24["total"] == 15825 and o24["fee"] == 150
    assert o24["monthly"] == pytest.approx(659.38) and o24["total_cost"] == 15975
    assert 6 < o24["apr"] < 6.5
    o12 = next(o for o in bank_a["options"] if o["months"] == 12)
    assert not o12["dbr_ok"]          # 1,284/month pushes debts above 33% of salary
    assert r["dbr"]["current_pct"] == pytest.approx(24.14) and r["dbr"]["limit"] == 33.33


def test_apr_and_fee_cap():
    assert loans.quote(1_000_000, loans.LENDERS[0], 12)["fee"] == 5000
    assert loans.apr(10000, 0, 10000 / 12, 12) == 0.0
    assert 5.0 < loans.apr(12000, 0, 1050, 12) < 23


def test_wishlist_accepts_loan_methods(client):
    ok = client.post("/api/wishlist", json={"name": "أثاث", "price": 15000, "method": "loan:bank_a:24"})
    assert ok.status_code == 200
    bad = client.post("/api/wishlist", json={"name": "أثاث", "price": 15000, "method": "loan:nobody:24"})
    assert bad.status_code == 422


def test_assistant_answers_in_english_without_llm(client):
    r = client.post("/api/chat", json={"message": "Can I get a 3000 phone in 4 payments?", "lang": "en"}).json()
    assert "Each payment is 750 SAR" in r["reply"] and "compare_scenarios" in r["tools"]
    r = client.post("/api/chat", json={"message": "Add a coffee expense 20", "lang": "en"}).json()
    assert r["actions"] and "قهوة" not in r["actions"][0]["summary"]
    assert "«coffee»" in r["actions"][0]["summary"].lower()
    assert client.post("/api/chat", json={"message": "hi", "lang": "fr"}).status_code == 422
