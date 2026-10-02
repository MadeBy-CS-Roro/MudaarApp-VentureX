"""Budget, entitlement and settlement regressions with isolated synthetic data."""
import pytest
from concurrent.futures import ThreadPoolExecutor
from test_mawid import client
import main
import service
import engine as E


def uid():
    with main.db.tx() as con:
        return con.execute("SELECT id FROM users LIMIT 1").fetchone()[0]


def switch(client, plan):
    response = client.post("/api/demo/subscription", json={"plan": plan})
    assert response.status_code == 200
    return response.json()


def test_budget_default_actual_and_warning(client):
    data = client.get("/api/budget").json()
    assert data["targets"] == {"essentials_pct": 70, "personal_pct": 20, "savings_pct": 10}
    actual = {row["id"]: row for row in data["actual"]}
    assert actual["essentials"]["amount"] == 7600 and actual["essentials"]["pct"] == 87
    assert actual["personal"]["amount"] == 420
    assert actual["savings"]["amount"] == 0  # 1140 is historical, not this cycle.
    assert actual["remaining"]["amount"] == 680  # Includes reserved buffer.
    assert sum(row["amount"] for row in data["actual"]) == 8700
    assert data["warnings"][0]["message"] == "التزاماتك 87% من راتبك، أعلى من هدفك 70%"
    assert client.get("/api/summary").json()["available"] == 180


@pytest.mark.parametrize("values", [
    {"essentials_pct": 70, "personal_pct": 20, "savings_pct": 20},
    {"essentials_pct": -1, "personal_pct": 91, "savings_pct": 10},
    {"essentials_pct": 70.5, "personal_pct": 19.5, "savings_pct": 10},
    {"essentials_pct": True, "personal_pct": 89, "savings_pct": 10},
    {"essentials_pct": 70, "personal_pct": 20},
])
def test_budget_rejects_invalid_without_writing(client, values):
    assert client.put("/api/budget", json=values).status_code == 422
    assert client.get("/api/budget").json()["targets"]["essentials_pct"] == 70


def test_budget_saving_preference_shared_with_engine_and_assistant(client):
    body = {"essentials_pct": 75, "personal_pct": 20, "savings_pct": 5}
    assert client.put("/api/budget", json=body).status_code == 200
    saving = client.post("/api/offers", json={"price": 3000, "target_months": 3}).json()["save"]
    assert saving["max_monthly"] == 435 and saving["max_target"] == 1050
    assert all(p["amount"] <= 435 for p in saving["progress"])
    assert "5%" in client.post("/api/chat", json={"message": "متى أجمع 3000؟"}).json()["reply"]
    assert client.get("/api/summary").json()["available"] == 180


def test_budget_owned_by_user_and_persists_reinitialization(client):
    target = {"essentials_pct": 80, "personal_pct": 15, "savings_pct": 5}
    client.put("/api/budget", json=target)
    main.db.init()
    assert client.get("/api/budget").json()["targets"] == target
    with main.db.tx() as con:
        result = service.connect_bank(con, "another-synthetic-user", "demo1")
        from budget import targets
        assert targets(con, result["user_id"])["savings_pct"] == 10
        assert targets(con, uid()) == target


def test_personal_heads_up_and_over_limit(client):
    # At 80% of target 1740 = 1392.
    client.post("/api/expenses", json={"name": "مصروف شخصي", "amount": 972, "category": "flexible:أخرى"})
    alerts = client.get("/api/summary").json()["alerts"]
    assert any(a["type"] == "personal_budget_heads_up" for a in alerts)
    client.post("/api/expenses", json={"name": "مصروف إضافي", "amount": 349, "category": "flexible:أخرى"})
    alerts = client.get("/api/summary").json()["alerts"]
    assert any(a["message"] == "صرفك الشخصي تعدّى 20% من راتبك هالشهر" for a in alerts if "message" in a)


def test_zero_savings_target_never_invents_reach_date(client):
    client.put("/api/budget", json={"essentials_pct": 80, "personal_pct": 20, "savings_pct": 0})
    data = client.post("/api/offers", json={"price": 3000, "target_months": 3}).json()["save"]
    assert data["max_target"] == 0 and data["required_months"] is None
    assert not data["reachable_in_target"]
    assert all(row["amount"] == 0 for row in data["progress"])


def test_savings_deadline_exact_examples_and_alternatives(client):
    data = client.post("/api/offers", json={"price": 3000, "target_months": 3}).json()
    assert data["best_offer_id"] == "tabby4"
    best = next(o for o in data["offers"] if o["id"] == data["best_offer_id"])
    assert best["earliest"] == 1 and best["start_tight"] == 150 and best["reason"]
    saving = data["save"]
    assert saving["max_target"] == 1920 and saving["required_months"] == 5
    assert saving["buyK"] == 4 and not saving["reachable_in_target"]
    for price, months in [(3000, 5), (1920, 3)]:
        assert client.post("/api/offers", json={"price": price, "target_months": months}).json()["save"]["reachable_in_target"]


@pytest.mark.parametrize("months", [0, 37, 1.5, True])
def test_deadline_validation(client, months):
    assert client.post("/api/offers", json={"price": 3000, "target_months": months}).status_code == 422


def test_demo_plus_default_and_backend_gates(client):
    assert client.get("/api/account").json()["subscription"]["id"] == "plus"
    assert client.get("/api/smart-account").status_code == 200
    assert client.get("/api/forecast").status_code == 403
    switch(client, "basic")
    for method, path, body in [("GET", "/api/smart-account", None), ("GET", "/api/forecast", None),
                               ("POST", "/api/offers", {"price": 3000}),
                               ("POST", "/api/scenarios", {"price": 3000})]:
        response = client.request(method, path, json=body)
        assert response.status_code == 403 and "ترقّ" in response.json()["detail"]
    assert client.get("/api/summary").json()["available"] == 180
    wishes = client.get("/api/wishlist").json()["items"]
    assert all(w["status"]["whenK"] in (None, 0) for w in wishes)
    assert all(not w.get("saving", {}).get("progress") for w in wishes)
    switch(client, "premium")
    assert len(client.get("/api/forecast").json()["months"]) == 12
    assert client.get("/api/forecast").json()["months"][0]["available"] == 180


def test_subscription_caps_visible_data_and_creation(client):
    data = client.get("/api/obligations").json()
    assert data["total_count"] > 5
    switch(client, "basic")
    data = client.get("/api/obligations").json()
    assert len(data["active_items"]) == 5 and data["hidden_count"] == data["total_count"] - 5
    assert "ترقّ" in data["locked_message"] and data["total"] == 7600
    response = client.post("/api/plans", json={"name": "اشتراك", "amount": 1, "day": 2, "kind": "recurring"})
    assert response.status_code == 403


def test_plus_limit_premium_unlimited_hidden_plan_mutation_blocked(client):
    user_id = uid()
    with main.db.tx() as con:
        for i in range(31):
            con.execute("INSERT INTO plans(id,user_id,name,merchant,kind,amount,day) VALUES (?,?,?,?,'recurring',1,2)",
                        (f"manual_extra_{i}", user_id, f"اشتراك {i}", f"MANUAL:{i}"))
    plus = client.get("/api/obligations").json()
    assert len(plus["active_items"]) == 30 and plus["hidden_count"] > 0
    visible = {p["id"] for p in client.get("/api/plans").json()["plans"]}
    hidden = next(f"manual_extra_{i}" for i in range(31) if f"manual_extra_{i}" not in visible)
    assert client.post(f"/api/plans/{hidden}/confirm", json={"amount": 2}).status_code == 403
    assert client.delete(f"/api/plans/{hidden}").status_code == 403
    assert client.post(f"/api/plans/{hidden}/pay-all").status_code == 403
    switch(client, "premium")
    data = client.get("/api/obligations").json()
    assert data["limit"] is None and data["hidden_count"] == 0 and len(data["active_items"]) == data["total_count"]
    assert client.post("/api/plans", json={"name": "جديد", "amount": 1, "day": 2, "kind": "recurring"}).status_code == 200


def test_subscription_switch_tenant_isolation_and_production_rejection(client, monkeypatch):
    switch(client, "premium")
    with main.db.tx() as con:
        result = service.connect_bank(con, "separate-demo-user", "demo1")
        import subscriptions
        assert subscriptions.current(con, result["user_id"])["id"] == "plus"
    assert client.get("/api/subscriptions").json()["current"]["id"] == "premium"
    main.db.init()
    assert client.get("/api/subscriptions").json()["current"]["id"] == "premium"
    monkeypatch.setattr(main, "DEMO_MODE", False)
    # A real authenticated request reaches the demo-only route guard.
    main.app.dependency_overrides[main.current_user] = lambda: {"id": uid(), "hash": "synthetic"}
    try:
        assert client.post("/api/demo/subscription", json={"plan": "basic"}).status_code == 404
        assert client.get("/api/subscriptions").json()["current"]["id"] == "premium"
    finally:
        main.app.dependency_overrides.pop(main.current_user, None)


def test_pay_all_tamara_quote_idempotency_and_month_archive(client):
    data = client.get("/api/obligations").json()
    tamara = next(p for p in data["active_items"] if "تمارا" in p["name"])
    tabby = next(p for p in data["active_items"] if "تابي" in p["name"])
    assert tamara["pay_all_total"] == 600
    response = client.post(f"/api/plans/{tamara['id']}/pay-all")
    assert response.status_code == 200 and response.json()["amount"] == 600
    assert client.post(f"/api/plans/{tamara['id']}/pay-all").json()["already_paid"]
    assert client.get("/api/summary").json()["available"] == -420  # Prepay 600 extra, retain this cycle's already-paid 600.
    assert client.post(f"/api/plans/{tamara['id']}/confirm", json={"remaining": 3}).status_code == 409
    with main.db.tx() as con:
        assert con.execute("SELECT COUNT(*) FROM plan_settlements").fetchone()[0] == 1
    client.post("/api/demo/next-month")
    data = client.get("/api/obligations").json()
    assert tabby["id"] in {p["id"] for p in data["previous_payments"]}
    assert tabby["id"] not in {p["id"] for p in data["active_items"]}
    assert tamara["id"] in {p["id"] for p in data["previous_payments"]}


def test_budget_and_settlement_reset_clear_safely(client):
    data = client.get("/api/obligations").json()
    tamara = next(p for p in data["active_items"] if "تمارا" in p["name"])
    client.post(f"/api/plans/{tamara['id']}/pay-all")
    client.post("/api/demo/next-month")
    assert client.post("/api/demo/reset").status_code == 200
    assert client.get("/api/summary").json()["available"] == 180
    with main.db.tx() as con:
        assert con.execute("SELECT COUNT(*) FROM plan_settlements").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM savings_deposits").fetchone()[0] == 0


def test_plan_limit_cannot_be_bypassed_by_concurrent_creation(client):
    data = client.get("/api/obligations").json()
    with main.db.tx() as con:
        for i in range(29-data["total_count"]):
            con.execute("INSERT INTO plans(id,user_id,name,merchant,kind,amount,day) "
                        "VALUES (?,?,?,?,'recurring',1,2)",
                        (f"concurrent_{i}", uid(), "اشتراك", f"MANUAL:{i}"))
    def create(i):
        return client.post("/api/plans", json={"name": f"جديد {i}", "amount": 1,
                                               "day": 2, "kind": "recurring"}).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, [1, 2])) == [200, 403]
    assert client.get("/api/obligations").json()["total_count"] == 30