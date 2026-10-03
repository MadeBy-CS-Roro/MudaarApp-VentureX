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
    sub = main.security.verify_token(hd["Authorization"][7:])["sub"]
    token = main.security.sign_token({"sub": sub, "mode": "production"})
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


def test_each_quick_demo_visitor_gets_a_private_copy(app_client):
    a, b = demo(app_client), demo(app_client)
    assert app_client.get("/api/summary", headers=a).json()["available"] == 180
    app_client.post("/api/payments/pay", json={"item_ids": ["tamara"]}, headers=a)
    app_client.post("/api/wishlist", json={"name": "ساعة", "price": 900, "method": "save"}, headers=a)
    assert app_client.get("/api/payments/due", headers=b).json()["payable_total"] == 600
    assert "ساعة" not in [w["name"] for w in app_client.get("/api/wishlist", headers=b).json()["items"]]


def test_old_demo_guests_are_cleaned_up_but_real_users_stay(app_client):
    demo(app_client)
    real = signup(app_client)
    with main.db.tx() as con:
        con.execute("UPDATE users SET created_at='2020-01-01 00:00:00'")
        removed = main.auth.cleanup_demo_guests(con)
        assert removed == 1
        assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
    assert app_client.get("/api/auth/me", headers=h(real["token"])).status_code == 200


def test_edit_personal_info_and_phone(app_client):
    hd = demo(app_client)
    r = app_client.patch("/api/account", json={"display_name": "نورة العتيبي", "email": "n@example.com"}, headers=hd)
    assert r.status_code == 200 and r.json()["display_name"] == "نورة العتيبي" and r.json()["email"] == "n@example.com"
    assert app_client.patch("/api/account", json={"email": "not-an-email"}, headers=hd).status_code == 422
    code = app_client.post("/api/account/phone", json={"phone": "0557778889"}, headers=hd).json()["demo_code"]
    assert app_client.post("/api/account/phone/verify", json={"phone": "0557778889", "code": "000000" if code != "000000" else "111111"}, headers=hd).status_code == 400
    ok = app_client.post("/api/account/phone/verify", json={"phone": "0557778889", "code": code}, headers=hd)
    assert ok.status_code == 200 and ok.json()["phone_masked"] == "05XX XXX 889"
    # the new number now logs in to the same account
    login = app_client.post("/api/auth/login", json={"phone": "0557778889"}).json()
    v = app_client.post("/api/auth/verify", json={"phone": "0557778889", "code": login["demo_code"]}).json()
    assert v["name"] == "نورة العتيبي"
    # a number used by someone else can't be taken
    signup(app_client, phone="0551231234", name="خالد")
    assert app_client.post("/api/account/phone", json={"phone": "0551231234"}, headers=hd).status_code == 409


def test_basic_plan_limits_apply_to_the_assistant(app_client):
    hd = demo(app_client)
    app_client.post("/api/demo/subscription", json={"plan": "basic"}, headers=hd)
    r = app_client.post("/api/chat", json={"message": "أقدر آخذ جوال بـ 3000 على 4 دفعات؟"}, headers=hd).json()
    assert "مو ضمن باقتك" in r["reply"] and not r["tools"]
    app_client.post("/api/plans", json={"name": "خامس", "amount": 10, "day": 3, "kind": "recurring"}, headers=hd)
    with main.db.tx() as con:
        uid = con.execute("SELECT id FROM users WHERE is_demo_guest=1").fetchone()["id"]
        import assistant
        with __import__("pytest").raises(assistant.PlanLocked):
            assistant.run_tool(con, uid, "add_obligation", {"name": "سادس", "amount": 10, "day": 3, "kind": "recurring"})
    for _ in range(4):
        assert app_client.post("/api/chat", json={"message": "كم عليّ هالشهر؟"}, headers=hd).status_code == 200
    assert app_client.post("/api/chat", json={"message": "كم عليّ هالشهر؟"}, headers=hd).status_code == 429


def test_plans_describe_cumulative_features(app_client):
    hd = demo(app_client)
    tiers = app_client.get("/api/subscriptions", headers=hd).json()["tiers"]
    assert [t["includes_previous"] for t in tiers] == [None, "الأساسية", "بلس"]
    assert any("5 التزامات" in f for f in tiers[0]["features"])
    assert any("30 التزام" in f for f in tiers[1]["features"]) and any("بلا حد" in f for f in tiers[2]["features"])


def test_assistant_adds_commitment_up_to_the_limit(app_client):
    hd = demo(app_client)
    app_client.post("/api/demo/subscription", json={"plan": "basic"}, headers=hd)
    r = app_client.post("/api/chat", json={"message": "ضيف التزام نادي 150 يوم 5"}, headers=hd).json()
    assert r["actions"] and "نادي" in r["actions"][0]["summary"]           # the 5th fits: confirmation card
    assert app_client.post(f"/api/chat/actions/{r['actions'][0]['id']}/confirm", headers=hd).status_code == 200
    r = app_client.post("/api/chat", json={"message": "ضيف التزام سباحة 100 يوم 9"}, headers=hd).json()
    assert not r["actions"] and "5" in r["reply"]                           # the 6th is refused with the limit


def test_score_is_fair_and_explained(app_client):
    hd = demo(app_client)
    s = app_client.get("/api/score", headers=hd).json()
    assert 0 <= s["score"] <= 100 and len(s["parts"]) == 6
    assert sum(p["max"] for p in s["parts"]) == 100
    parts = {p["id"]: p for p in s["parts"]}
    assert parts["on_time"]["points"] == 25                      # nothing late
    assert parts["essentials"]["points"] < 15 and parts["essentials"]["tip"]   # 87% vs 70% target
    # fairness: same behaviour on a much bigger salary scores the same (score uses ratios, not amounts)
    with main.db.tx() as con:
        uid = con.execute("SELECT id FROM users WHERE is_demo_guest=1").fetchone()["id"]
        con.execute("UPDATE transactions SET amount=amount*4 WHERE user_id=?", (uid,))
        con.execute("UPDATE plans SET amount=amount*4 WHERE user_id=?", (uid,))
    assert app_client.get("/api/score", headers=hd).json()["score"] == s["score"]


def test_good_actions_earn_points(app_client):
    hd = demo(app_client)
    before = app_client.get("/api/score", headers=hd).json()["points"]
    app_client.post("/api/payments/pay", json={"item_ids": ["tamara"]}, headers=hd)          # paid before due: +10
    app_client.post("/api/plans/tabby/confirm", json={}, headers=hd)                          # +2
    app_client.post("/api/plans/tabby/confirm", json={}, headers=hd)                          # no double points
    after = app_client.get("/api/score", headers=hd).json()
    assert after["points"] - before >= 12
    assert {e["label"] for e in after["events"]} >= {"دفعت التزام قبل موعده", "أكدت التزام"}


def test_standings_are_private_by_default(app_client):
    hd = demo(app_client)
    lb = app_client.get("/api/leaderboard", headers=hd).json()
    assert lb["opt_in"] is False and lb["total"] >= 15 and any(r["me"] for r in lb["rows"])
    assert all(set(r) == {"name", "score", "me", "rank"} for r in lb["rows"])       # no money data at all
    assert app_client.put("/api/leaderboard/me", json={"opt_in": True}, headers=hd).status_code == 422
    lb = app_client.put("/api/leaderboard/me", json={"opt_in": True, "nickname": "نجمة"}, headers=hd).json()
    assert lb["opt_in"] and next(r for r in lb["rows"] if r["me"])["name"] == "نجمة"
    other = demo(app_client)
    names = [r["name"] for r in app_client.get("/api/leaderboard", headers=other).json()["rows"]]
    assert "نجمة" in names


def test_obligations_link_to_each_provider(app_client):
    hd = demo(app_client)
    o = app_client.get("/api/obligations", headers=hd).json()
    urls = {p["url"] for p in o["payees"]}
    assert {"https://tamara.co", "https://tabby.ai", "https://www.ejar.sa", "https://www.se.com.sa"} <= urls


def test_wishlist_keeps_plan_type(app_client):
    hd = demo(app_client)
    r = app_client.post("/api/wishlist", json={"name": "سفرة الرياض", "price": 6000, "method": "save", "kind": "trip"}, headers=hd)
    assert r.status_code == 200 and next(i for i in r.json()["items"] if i["name"] == "سفرة الرياض")["kind"] == "trip"
