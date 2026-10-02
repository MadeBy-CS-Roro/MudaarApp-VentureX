"""Login (phone + one-time code), per-user bank data, pay-all, categories."""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setattr(main.db, "DB_PATH", str(tmp_path / "mudar-auth.db"))
    monkeypatch.setattr(main, "limiter", main.security.RateLimiter())
    monkeypatch.setattr(main, "auth_ip_limiter", main.security.RateLimiter(limit=1000))
    monkeypatch.setattr(main, "auth_phone_limiter", main.security.RateLimiter(limit=1000))
    monkeypatch.setattr(main, "ALLOW_ANON", False)
    monkeypatch.setattr(main.assistant, "API_KEY", None)
    with TestClient(main.app) as c:
        yield c


def signup(c, phone="0551234567", name="سارة"):
    r = c.post("/api/auth/signup", json={"name": name, "phone": phone, "email": "", "accept_terms": True})
    assert r.status_code == 200, r.text
    r = c.post("/api/auth/verify", json={"phone": phone, "code": r.json()["demo_code"]})
    assert r.status_code == 200, r.text
    return r.json()


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_no_token_is_rejected(app_client):
    assert app_client.get("/api/summary").status_code == 401
    assert app_client.post("/api/consent", json={"bank_id": "demo1"}).status_code == 401


def test_signup_verify_connect_and_isolation(app_client):
    a = signup(app_client)
    assert a["bank_connected"] is False and a["name"] == "سارة"
    assert app_client.get("/api/auth/me", headers=h(a["token"])).json()["bank_connected"] is False
    assert app_client.post("/api/consent", json={"bank_id": "demo1"}, headers=h(a["token"])).status_code == 200
    assert app_client.get("/api/auth/me", headers=h(a["token"])).json()["bank_connected"] is True
    assert app_client.get("/api/summary", headers=h(a["token"])).json()["available"] == 180
    acc = app_client.get("/api/account", headers=h(a["token"])).json()
    assert acc["display_name"] == "سارة" and acc["phone_masked"] == "05XX XXX 567"

    b = signup(app_client, phone="0559876543", name="خالد")
    app_client.post("/api/consent", json={"bank_id": "demo1"}, headers=h(b["token"]))
    app_client.post("/api/wishlist", json={"name": "ساعة", "price": 900, "method": "save"}, headers=h(a["token"]))
    names_b = [w["name"] for w in app_client.get("/api/wishlist", headers=h(b["token"])).json()["items"]]
    assert "ساعة" not in names_b


def test_duplicate_signup_and_login_message(app_client):
    signup(app_client)
    r = app_client.post("/api/auth/signup", json={"name": "سارة", "phone": "0551234567", "accept_terms": True})
    assert r.status_code == 409
    unknown = app_client.post("/api/auth/login", json={"phone": "0550000999"}).json()
    known = app_client.post("/api/auth/login", json={"phone": "0551234567"}).json()
    assert unknown["message"] == known["message"] and "demo_code" not in unknown
    assert app_client.post("/api/auth/verify", json={"phone": "0551234567", "code": known["demo_code"]}).status_code == 200


def test_wrong_code_lock_and_expiry(app_client):
    signup(app_client)
    code = app_client.post("/api/auth/login", json={"phone": "0551234567"}).json()["demo_code"]
    wrong = "000000" if code != "000000" else "111111"
    statuses = [app_client.post("/api/auth/verify", json={"phone": "0551234567", "code": wrong}).status_code
                for _ in range(5)]
    assert statuses[:4] == [400] * 4 and statuses[4] == 429
    assert app_client.post("/api/auth/verify", json={"phone": "0551234567", "code": code}).status_code == 429

    with main.db.tx() as con:
        con.execute("DELETE FROM otp_codes")
    code = app_client.post("/api/auth/login", json={"phone": "0551234567"}).json()["demo_code"]
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with main.db.tx() as con:
        con.execute("UPDATE otp_codes SET expires_at=?", (past,))
    r = app_client.post("/api/auth/verify", json={"phone": "0551234567", "code": code})
    assert r.status_code == 400 and "انتهى" in r.json()["detail"]


def test_bad_phone_and_terms(app_client):
    assert app_client.post("/api/auth/signup", json={"name": "سارة", "phone": "12345", "accept_terms": True}).status_code == 422
    assert app_client.post("/api/auth/signup", json={"name": "سارة", "phone": "0551234567", "accept_terms": False}).status_code == 422


def test_production_never_returns_codes(app_client, monkeypatch):
    monkeypatch.setattr(main, "DEMO_MODE", False)
    r = app_client.post("/api/auth/signup", json={"name": "سارة", "phone": "0551234567", "accept_terms": True})
    assert r.status_code == 501 and "demo_code" not in r.text
    assert app_client.post("/api/auth/demo").status_code == 404


def demo(c):
    r = c.post("/api/auth/demo")
    assert r.status_code == 200
    return h(r.json()["token"])


def test_quick_demo_login_and_pay_all(app_client):
    hd = demo(app_client)
    due = app_client.get("/api/payments/due", headers=hd).json()
    assert [i["name"] for i in due["payable"]] == ["تمارا"] and due["payable_total"] == 600
    assert any(i["id"] == "auto_finance" for i in due["auto"])
    before = app_client.get("/api/summary", headers=hd).json()
    assert any(a["type"] == "before_salary" for a in before["alerts"])

    assert app_client.post("/api/payments/pay", json={"item_ids": ["auto_finance"]}, headers=hd).status_code == 422
    r = app_client.post("/api/payments/pay", json={"item_ids": ["tamara"]}, headers=hd)
    assert r.status_code == 200 and r.json()["total"] == 600 and r.json()["due"]["payable"] == []
    after = app_client.get("/api/summary", headers=hd).json()
    assert not any(a["type"] == "before_salary" for a in after["alerts"])
    assert after["available"] == before["available"] == 180
    tamara = next(p for p in after["plans"] if p["id"] == "tamara")
    assert tamara["status"] == "paid"
    assert app_client.post("/api/payments/pay", json={"item_ids": ["tamara"]}, headers=hd).status_code == 422


def test_pay_mode_toggle_and_production(app_client, monkeypatch):
    hd = demo(app_client)
    r = app_client.patch("/api/plans/tamara", json={"pay_mode": "auto"}, headers=hd).json()
    assert r["payable"] == [] and any(i["id"] == "tamara" for i in r["auto"])
    app_client.patch("/api/plans/tamara", json={"pay_mode": "manual"}, headers=hd)
    monkeypatch.setattr(main, "DEMO_MODE", False)
    original = main.security.verify_token(hd["Authorization"].removeprefix("Bearer "))
    token = main.security.sign_token({"sub": original["sub"], "mode": "production"})
    monkeypatch.setattr(main, "PRODUCTION_MODE", True)
    r = app_client.post("/api/payments/pay", json={"item_ids": ["tamara"]}, headers=h(token))
    assert r.status_code == 501


def test_fixed_categories(app_client):
    hd = demo(app_client)
    cats = app_client.get("/api/categories").json()["groups"]
    assert "مطاعم ومقاهي" in cats[1]["items"] and "وقود" in cats[0]["items"]
    ok = app_client.post("/api/expenses", json={"name": "تذكرة", "amount": 50, "category": "flexible:سفر"}, headers=hd)
    assert ok.status_code == 200
    bad = app_client.post("/api/expenses", json={"name": "x", "amount": 5, "category": "flexible:شي غريب"}, headers=hd)
    assert bad.status_code == 422
    flex = app_client.get("/api/summary", headers=hd).json()["categories"]["flexible"]
    assert "مطاعم ومقاهي" in flex


def test_completed_obligation_moves_to_previous(app_client):
    hd = demo(app_client)
    app_client.post("/api/demo/next-month", headers=hd)
    data = app_client.get("/api/obligations", headers=hd).json()
    assert any(p["name"] == "تابي" for p in data["previous_payments"])
    assert not any(p["name"] == "تابي" for p in data["active_items"])
