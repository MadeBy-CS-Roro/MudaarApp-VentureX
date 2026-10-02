"""Phone API regressions; always uses synthetic data and temporary databases."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from test_mawid import client
import main
import actions
import engine as E
import language


def user():
    with main.db.tx() as con:
        return dict(con.execute("SELECT id,user_hash AS hash FROM users LIMIT 1").fetchone())


def propose(tool, params):
    with main.db.tx() as con:
        return actions.propose(con, user()["id"], tool, params)


def test_obligations_total_does_not_double_count_bills(client):
    data = client.get("/api/obligations").json()
    assert data["total"] == 7600
    assert data["plans_total"] == 4100
    assert data["essentials_total"] == 3500
    assert data["bills_total"] > 0
    assert sum(data["essentials_by_category"].values()) == 3500
    assert any(p["type"] == "bill" and not p["in_formula"] for p in data["items"])
    assert client.get("/api/summary").json()["available"] == 180


def test_manual_expense_changes_balance_and_deletes(client):
    r = client.post("/api/expenses", json={"name": "قهوة", "amount": 20, "category": "flexible:قهوة"})
    assert r.status_code == 200
    item = next(i for i in r.json()["items"] if i["source"] == "manual")
    assert r.json()["flexible_total"] == 440
    assert client.get("/api/summary").json()["available"] == 160
    bank = next(i for i in r.json()["items"] if i["source"] == "bank")
    assert client.delete(f"/api/expenses/{bank['id']}").status_code == 404
    assert client.delete(f"/api/expenses/{item['id']}").status_code == 200
    assert client.get("/api/summary").json()["available"] == 180
    assert client.delete(f"/api/expenses/{item['id']}").status_code == 404


def test_manual_plan_add_confirm_delete(client):
    r = client.post("/api/plans", json={"name": "اشتراك", "amount": 100, "day": 10, "kind": "recurring"})
    assert r.status_code == 200
    pid = r.json()["id"]
    assert client.get("/api/obligations").json()["total"] == 7700
    assert client.get("/api/summary").json()["available"] == 80
    assert client.post(f"/api/plans/{pid}/confirm", json={"amount": 50, "remaining": 2}).status_code == 200
    assert client.get("/api/summary").json()["available"] == 130
    assert client.delete(f"/api/plans/{pid}").status_code == 200
    assert client.get("/api/obligations").json()["total"] == 7600
    assert client.delete(f"/api/plans/{pid}").status_code == 404


def test_completed_plans_remain_visible_not_counted(client):
    client.post("/api/plans/tabby/confirm", json={"remaining": 0})
    data = client.get("/api/obligations").json()
    plan = next(p for p in data["items"] if p["id"] == "tabby")
    assert plan["status"] == "completed"
    assert plan["progress"] == 100
    assert data["total"] == 7300


def test_offer_selection_and_save_first_exact_numbers(client):
    r = client.post("/api/offers", json={"price": 3000})
    assert r.status_code == 200
    data = r.json()
    assert data["best_offer_id"] == "tabby4"
    best = next(o for o in data["offers"] if o["id"] == "tabby4")
    assert best["monthly"] == 750 and best["total"] == 3000 and best["extra_cost"] == 0
    assert best["earliest"] == 1 and best["start_tight"] == 150 and not best["ok"]
    assert best["tight"] == -570
    assert all(o["sample"] for o in data["offers"])
    saving = data["save"]
    assert saving["monthly"] == 180 and saving["max_monthly"] == 870
    assert saving["buyK"] == 4 and saving["buy_label"] == "بعد 4 شهور"
    assert [p["amount"] for p in saving["progress"]] == [180, 870, 870, 870, 210]
    assert saving["progress"][-1]["cumulative"] == 3000
    assert saving["progress"][-1]["pct"] == 100


def test_best_offer_fitting_now_first_then_cost(client):
    data = client.post("/api/offers", json={"price": 600}).json()
    assert data["best_offer_id"] == "tabby4"  # fee-free 150 fits now; fee-free 3*200 does not
    assert next(o for o in data["offers"] if o["id"] == data["best_offer_id"])["ok"]
    data = client.post("/api/offers", json={"price": 300}).json()
    assert data["best_offer_id"] == "tabby4"  # both fee-free fit; lower monthly


def test_generalized_schedules_preserve_existing_functions(client):
    assert E.schedule("cash", 3000) == ([3000], 3000)
    assert E.schedule("bnpl4", 3000) == ([750] * 4, 3000)
    assert E.schedule("fin12", 3000) == ([275] * 12, 3300)
    assert E.payment_schedule(5, 2500) == [500] * 5
    for count, cost in [(0, 2500), (2, -1)]:
        with pytest.raises(ValueError):
            E.payment_schedule(count, cost)


def test_saving_caps_zero_balance_and_wishlist_month_simulation(client):
    client.post("/api/expenses", json={"name": "مصروف", "amount": 200, "category": "flexible:غير مصنف"})
    saving = client.post("/api/offers", json={"price": 3000}).json()["save"]
    assert saving["monthly"] == 0
    assert all(0 <= p["amount"] <= 870 for p in saving["progress"])
    client.post("/api/demo/reset")
    created = client.post("/api/wishlist", json={"name": "جوال", "price": 3000, "method": "save"}).json()
    item = next(i for i in created["items"] if i["name"] == "جوال")
    assert item["when_label"] == "بعد 4 شهور"
    client.post("/api/demo/next-month")
    item = next(i for i in client.get("/api/wishlist").json()["items"] if i["name"] == "جوال")
    assert item["saved"] == 180
    client.post("/api/demo/next-month")
    item = next(i for i in client.get("/api/wishlist").json()["items"] if i["name"] == "جوال")
    assert item["saved"] == 1050


@pytest.mark.parametrize("message,tool,endpoint", [
    ("ضيف مصروف قهوة 20", "add_expense", "/api/expenses"),
    ("حط الجوال بالأمنيات", "add_to_wishlist", "/api/wishlist"),
])
def test_fallback_proposes_only_and_confirm_applies_once(client, message, tool, endpoint):
    before = client.get(endpoint).json()
    result = client.post("/api/chat", json={"message": message}).json()
    assert result["mode"] == "rules"
    assert result["tools"] == [tool]
    assert client.get(endpoint).json() == before
    action = result["actions"][0]
    assert (datetime.fromisoformat(action["expires_at"]) - datetime.fromisoformat(action["created_at"])).seconds == 600
    path = f"/api/chat/actions/{action['id']}/confirm"
    assert client.post(path).status_code == 200
    after = client.get(endpoint).json()
    assert before != after
    assert client.post(path).status_code == 409
    assert client.get(endpoint).json() == after
    with main.db.tx() as con:
        assert con.execute("SELECT COUNT(*) FROM audit_log WHERE action='chat.action.confirmed'").fetchone()[0] == 1


def test_cancel_expiry_and_other_user_fail(client):
    payload = {"name": "قهوة", "amount": 20, "category": "flexible:قهوة"}
    a = propose("add_expense", payload)
    assert client.post(f"/api/chat/actions/{a['id']}/cancel").status_code == 200
    assert client.post(f"/api/chat/actions/{a['id']}/confirm").status_code == 409
    a = propose("add_expense", payload)
    with main.db.tx() as con:
        con.execute("UPDATE pending_actions SET expires_at=? WHERE id=?",
                    ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(), a["id"]))
    assert client.post(f"/api/chat/actions/{a['id']}/confirm").status_code == 409
    assert client.post(f"/api/chat/actions/{a['id']}/cancel").status_code == 409
    a = propose("add_expense", payload)
    hash_ = main.security.hash_id("phone-other-user")
    with main.db.tx() as con:
        con.execute("INSERT INTO users(user_hash,display_name) VALUES (?,?)", (hash_, "other"))
    headers = {"Authorization": "Bearer " + main.security.sign_token({"sub": hash_, "mode": "demo"})}
    assert client.post(f"/api/chat/actions/{a['id']}/confirm", headers=headers).status_code == 404
    assert client.post(f"/api/chat/actions/{a['id']}/cancel", headers=headers).status_code == 404
    assert client.get("/api/summary").json()["available"] == 180
    assert client.post(f"/api/chat/actions/{a['id']}/confirm").status_code == 200


def test_simultaneous_confirm_only_one_wins(client):
    a = propose("add_expense", {"name": "قهوة", "amount": 20, "category": "flexible:قهوة"})
    path = f"/api/chat/actions/{a['id']}/confirm"
    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: client.post(path).status_code, range(2)))
    assert sorted(statuses) == [200, 409]
    assert client.get("/api/summary").json()["available"] == 160


@pytest.mark.parametrize("tool,params", [
    ("add_obligation", {"name": "اشتراك", "amount": 50, "day": 12, "kind": "recurring"}),
    ("update_plan", {"plan_id": "tamara", "amount": 650}),
    ("delete_obligation", {"plan_id": "tamara"}),
    ("set_category", {"merchant": "COFFEE", "category": "flexible:قهوة"}),
])
def test_all_other_write_tools_are_pending_and_confirmed(client, tool, params):
    with main.db.tx() as con:
        before = con.total_changes
        out = main.assistant.run_tool(con, user()["id"], tool, params)
        assert "action" in out
        assert con.total_changes - before == 1  # only proposal insertion
    assert client.post(f"/api/chat/actions/{out['action']['id']}/confirm").status_code == 200


def test_remove_wishlist_and_invalid_tool_params(client):
    wish = client.get("/api/wishlist").json()["items"][0]
    a = propose("remove_from_wishlist", {"item_id": wish["id"]})
    assert any(w["id"] == wish["id"] for w in client.get("/api/wishlist").json()["items"])
    assert client.post(f"/api/chat/actions/{a['id']}/confirm").status_code == 200
    assert client.get("/api/wishlist").json()["items"] == []
    with main.db.tx() as con:
        for tool, p in [("add_expense", {"name": "قهوة", "amount": -20, "category": "flexible:قهوة"}),
                        ("update_plan", {"plan_id": "tamara"}),
                        ("delete_obligation", {"plan_id": "not-owned"}),
                        ("remove_from_wishlist", {"item_id": 100000})]:
            assert "error" in main.assistant.run_tool(con, user()["id"], tool, p)


def test_failed_action_rolls_back_claim(client):
    a = propose("delete_obligation", {"plan_id": "tamara"})
    client.delete("/api/plans/tamara")
    assert client.post(f"/api/chat/actions/{a['id']}/confirm").status_code == 404
    with main.db.tx() as con:
        assert con.execute("SELECT status FROM pending_actions WHERE id=?", (a["id"],)).fetchone()[0] == "pending"


def test_cross_user_expense_plan_isolation(client):
    r = client.post("/api/expenses", json={"name": "قهوة", "amount": 20, "category": "flexible:قهوة"}).json()
    expense = next(i for i in r["items"] if i["source"] == "manual")
    pid = client.post("/api/plans", json={"name": "اشتراك", "amount": 10, "day": 1}).json()["id"]
    other_hash = main.security.hash_id("other-phone")
    with main.db.tx() as con:
        con.execute("INSERT INTO users(user_hash,display_name) VALUES (?,?)", (other_hash, "other"))
    headers = {"Authorization": "Bearer " + main.security.sign_token({"sub": other_hash, "mode": "demo"})}
    assert client.delete(f"/api/expenses/{expense['id']}", headers=headers).status_code == 404
    assert client.delete(f"/api/plans/{pid}", headers=headers).status_code == 404
    assert client.post(f"/api/plans/{pid}/confirm", json={"amount": 1}, headers=headers).status_code == 404
    assert client.get("/api/expenses", headers=headers).json()["items"] == []
    assert any(p["id"] == pid for p in client.get("/api/plans").json()["plans"])


def test_contact_validation_rate_limit_and_account(client, monkeypatch):
    monkeypatch.setattr(main, "contact_limiter", main.security.RateLimiter(limit=2, window=60))
    assert client.post("/api/contact", json={"name": "", "message": "مرحبا"}).status_code == 422
    assert client.post("/api/contact", json={"name": "نورة", "message": "قصير"}).status_code == 422
    for _ in range(2):
        assert client.post("/api/contact", json={"name": "نورة", "message": "عندي سؤال عن موعد"}).status_code == 200
    assert client.post("/api/contact", json={"name": "نورة", "message": "عندي سؤال عن موعد"}).status_code == 429
    with main.db.tx() as con:
        assert con.execute("SELECT COUNT(*) FROM contacts").fetchone()[0] == 2
    info = client.get("/api/account").json()
    assert info["display_name"] == "نورة"
    assert info["phone_masked"] == "05XX XXX 123"
    assert info["salary_day"] == 27 and info["bank_id"] == "demo1"
    assert info["consent_expires_at"]
    assert [t["price"] for t in info["tiers"]] == [0, 29, 79]
    assert info["subscription"]["assistant_questions"] == 5


def test_revoke_removes_wishes_pending_categories(client):
    propose("add_expense", {"name": "قهوة", "amount": 20, "category": "flexible:قهوة"})
    assert client.delete("/api/consent").status_code == 200
    with main.db.tx() as con:
        for table in ("transactions", "plans", "wishlist", "pending_actions", "category_overrides"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_number_agreement_shared_forms(client):
    assert client.get("/api/language").json() == language.FORMS
    assert [language.counted(n) for n in [1, 2, 3, 10, 17]] == ["دفعة وحدة", "دفعتين", "3 دفعات", "10 دفعات", "17 دفعة"]
    assert [language.counted(n, "days") for n in [1, 2, 3, 30]] == ["يوم واحد", "يومين", "3 أيام", "30 يوم"]


def test_llm_write_tools_still_need_individual_confirmations(client, monkeypatch):
    import httpx
    monkeypatch.setattr(main.assistant, "API_KEY", "mock-api-key-for-test")
    replies = iter([
        {"content": [
            {"type": "tool_use", "id": "one", "name": "add_expense",
             "input": {"name": "قهوة", "amount": 20, "category": "flexible:قهوة"}},
            {"type": "tool_use", "id": "two", "name": "update_plan", "input": {"plan_id": "tamara", "amount": 650}}]},
        {"content": [{"type": "text", "text": "راجع الطلبين وأكّد كل طلب لحاله."}]},
    ])
    monkeypatch.setattr(main.assistant.httpx, "post", lambda *args, **kwargs:
                        httpx.Response(200, json=next(replies), request=httpx.Request("POST", "https://example.com")))
    result = client.post("/api/chat", json={"message": "ضيف قهوة وعدل تمارا"}).json()
    assert result["mode"] == "llm" and len(result["actions"]) == 2
    assert client.get("/api/summary").json()["available"] == 180
    assert client.post(f"/api/chat/actions/{result['actions'][0]['id']}/confirm").status_code == 200
    assert client.get("/api/summary").json()["available"] == 160  # only expense, not plan
    assert client.post(f"/api/chat/actions/{result['actions'][1]['id']}/confirm").status_code == 200
    assert client.get("/api/summary").json()["available"] == 110


def test_assistant_save_uses_same_capped_rule(client):
    result = client.post("/api/chat", json={"message": "أبي أجمع أول للجوال 3000"}).json()
    assert "بعد 4 شهور" in result["reply"] and "180" in result["reply"]
    assert result["tools"] == ["compare_offers"]


def test_free_plan_chat_quota_renews_next_month(client):
    for _ in range(5):
        assert client.post("/api/chat", json={"message": "كم عليّ هالشهر؟"}).status_code == 200
    assert client.post("/api/chat", json={"message": "كم عليّ هالشهر؟"}).status_code == 429
    subscription = client.get("/api/account").json()["subscription"]
    assert subscription["questions_used"] == 5 and subscription["questions_left"] == 0
    assert client.get("/api/summary").status_code == 200
    assert client.post("/api/demo/next-month").status_code == 200
    assert client.post("/api/chat", json={"message": "كم عليّ هالشهر؟"}).status_code == 200


def test_legacy_sqlite_source_migration_preserves_rows(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(main.db, "DB_PATH", path)
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE transactions(id INTEGER PRIMARY KEY,user_id INTEGER,date TEXT,amount REAL,"
                    "direction TEXT,merchant TEXT,description TEXT,category TEXT)")
        con.execute("INSERT INTO transactions VALUES (1,1,'2026-09-01',20,'debit','COFFEE','x','flexible:قهوة')")
    main.db.init()
    main.db.init()
    with main.db.tx() as con:
        row = con.execute("SELECT * FROM transactions").fetchone()
        assert row["amount"] == 20 and row["source"] == "bank"