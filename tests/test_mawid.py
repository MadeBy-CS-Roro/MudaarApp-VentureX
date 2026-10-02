"""Run: pytest -q   (uses a temporary database)"""
import os
import sys
import json
import subprocess

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient
import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Give each test a fresh database and initialized demo user."""
    monkeypatch.setattr(main.db, "DB_PATH", str(tmp_path / "mawid-test.db"))
    monkeypatch.setattr(main, "limiter", main.security.RateLimiter())
    monkeypatch.setattr(main.assistant, "API_KEY", None)
    main.assistant._history.clear()
    main.assistant._last.clear()

    with TestClient(main.app) as test_client:
        response = test_client.post("/api/consent", json={"bank_id": "demo1"})
        assert response.status_code == 200
        assert response.json()["plans_found"] == 4
        yield test_client


def test_plans_detected(client):
    plans = {p["id"]: p for p in client.get("/api/plans").json()["plans"]}
    assert plans["tamara"]["amount"] == 600 and plans["tamara"]["remaining"] == 2
    assert plans["tabby"]["remaining"] == 1
    assert plans["auto_finance"]["remaining"] == 18
    assert plans["ejar"]["remaining"] is None and plans["ejar"]["action"]["value"] == "123456789"


def test_confirm_plan_edits_update_plans_and_monthly_summary(client):
    response = client.post(
        "/api/plans/tamara/confirm",
        json={"amount": 850, "remaining": 3},
    )
    assert response.status_code == 200

    confirmed = {p["id"]: p for p in response.json()["plans"]}["tamara"]
    assert confirmed["amount"] == 850
    assert confirmed["remaining"] == 3
    assert confirmed["confirmed"] is True

    plans = {p["id"]: p for p in client.get("/api/plans").json()["plans"]}
    assert plans["tamara"]["amount"] == 850
    assert plans["tamara"]["remaining"] == 3

    summary = client.get("/api/summary").json()
    tamara = next(p for p in summary["plans"] if p["id"] == "tamara")
    assert tamara["amount"] == 850
    assert tamara["remaining"] == 3
    assert summary["formula"]["obligations"] == 4350
    assert summary["safe_to_spend"] == 350
    before_salary = next(a for a in summary["alerts"] if a["type"] == "before_salary")
    assert before_salary["amount"] == 850
    assert before_salary["plans"][0]["name"] == "تمارا"


def test_confirm_plan_with_zero_remaining_is_not_counted(client):
    response = client.post("/api/plans/tamara/confirm", json={"remaining": 0})
    assert response.status_code == 200
    confirmed = {p["id"]: p for p in response.json()["plans"]}["tamara"]
    assert confirmed["remaining"] == 0
    assert confirmed["confirmed"] is True

    plans = {p["id"]: p for p in client.get("/api/plans").json()["plans"]}
    assert plans["tamara"]["remaining"] == 0

    summary = client.get("/api/summary").json()
    assert "tamara" not in {p["id"] for p in summary["plans"]}
    assert summary["formula"]["obligations"] == 3500
    assert summary["safe_to_spend"] == 1200


@pytest.mark.parametrize(
    ("correction", "expected_amount", "expected_remaining"),
    [
        ({"amount": 850}, 850, 2),
        ({"remaining": 3}, 600, 3),
        ({}, 600, 2),
    ],
)
def test_confirm_plan_preserves_unedited_values_in_plans_and_summary(
    client, correction, expected_amount, expected_remaining
):
    response = client.post("/api/plans/tamara/confirm", json=correction)
    assert response.status_code == 200

    confirmed = {p["id"]: p for p in response.json()["plans"]}["tamara"]
    assert confirmed["amount"] == expected_amount
    assert confirmed["remaining"] == expected_remaining
    assert confirmed["confirmed"] is True

    plans = {p["id"]: p for p in client.get("/api/plans").json()["plans"]}
    assert plans["tamara"]["amount"] == expected_amount
    assert plans["tamara"]["remaining"] == expected_remaining
    assert plans["tamara"]["confirmed"] is True

    summary = client.get("/api/summary").json()
    tamara = next(p for p in summary["plans"] if p["id"] == "tamara")
    assert tamara["amount"] == expected_amount
    assert tamara["remaining"] == expected_remaining
    assert tamara["confirmed"] is True


def test_confirm_missing_plan_returns_not_found(client):
    response = client.post("/api/plans/missing-plan/confirm", json={"amount": 850, "remaining": 3})
    assert response.status_code == 404


def test_summary_numbers(client):
    s = client.get("/api/summary").json()
    assert s["formula"] == {"salary": 8700, "obligations": 4100, "essentials": 3500, "buffer": 500, "total_obligations": 7600}
    assert s["obligations_total"] == 7600
    assert s["safe_to_spend"] == 600 and s["spent"] == 420 and s["available"] == 180
    before = [a for a in s["alerts"] if a["type"] == "before_salary"][0]
    assert before["amount"] == 600 and before["plans"][0]["name"] == "تمارا"
    assert any(a["type"] == "plan_ending" and a["name"] == "تابي" for a in s["alerts"])

def _expense_payload(client, **changes):
    payload = {"amount": 35.75, "merchant": "مقهى", "category": "flexible:مطاعم ومقاهي",
               "date": client.get("/api/summary").json()["today"]}
    return {**payload, **changes}
def test_scenarios(client):
    r = client.post("/api/scenarios", json={"price": 3000}).json()
    assert r["bnpl4"]["tight"] == -570 and r["bnpl4"]["earliest"] == 1
    assert r["fin12"]["total"] == 3300
    assert r["cash"]["earliest"] is None
    assert r["save"]["buyK"] == 4


def test_chat_fallback_flow(client):
    a = client.post("/api/chat", json={"message": "أقدر آخذ جوال بـ 3000 على 4 دفعات؟"}).json()
    assert "750" in a["reply"] and "compare_scenarios" in a["tools"]
    b = client.post("/api/chat", json={"message": "طيب متى أقدر؟"}).json()
    assert "الشهر الجاي" in b["reply"] and "150" in b["reply"]
    c = client.post("/api/chat", json={"message": "طيب حطه بقائمة الأمنيات"}).json()
    assert c["tools"] == ["add_to_wishlist"]


def test_next_month_notifies(client):
    wish = client.post("/api/wishlist", json={"name": "جوال", "price": 3000, "method": "bnpl4"})
    assert wish.status_code == 200

    r = client.post("/api/demo/next-month").json()
    types = [e["type"] for e in r["events"]]
    assert "salary" in types
    assert any(e["type"] == "plan_end" and e["name"] == "تابي" for e in r["events"])
    phone = [e for e in r["events"] if e["type"] == "wish_affordable" and e["name"] == "جوال"][0]
    assert phone["tight"] == 150
    s = client.get("/api/summary").json()
    assert s["safe_to_spend"] == 900 and s["spent"] == 0


def test_wishlist_add_read_and_delete(client):
    first = client.post("/api/wishlist", json={"name": "كاميرا", "price": 2400, "method": "save"})
    assert first.status_code == 200
    item = next(item for item in first.json()["items"] if item["name"] == "كاميرا")
    assert item["price"] == 2400
    assert item["method"] == "save"

    second = client.post("/api/wishlist", json={"name": "سماعة", "price": 800, "method": "cash"})
    assert second.status_code == 200
    listed = client.get("/api/wishlist")
    assert listed.status_code == 200
    listed_names = [item["name"] for item in listed.json()["items"]]
    assert "سماعة" in listed_names and "كاميرا" in listed_names

    deleted = client.delete(f"/api/wishlist/{item['id']}")
    assert deleted.status_code == 200
    remaining_names = [entry["name"] for entry in deleted.json()["items"]]
    assert "كاميرا" not in remaining_names
    assert "سماعة" in remaining_names and "عمرة" in remaining_names
    assert [entry["name"] for entry in client.get("/api/wishlist").json()["items"]] == remaining_names


def test_repeated_wishlist_submission_returns_one_saved_item(client):
    payload = {"name": "سماعة", "price": 800, "method": "cash"}

    first = client.post("/api/wishlist", json=payload)
    assert first.status_code == 200
    first_matches = [item for item in first.json()["items"] if item["name"] == payload["name"]]
    assert len(first_matches) == 1

    second = client.post("/api/wishlist", json=payload)
    assert second.status_code == 200
    second_matches = [item for item in second.json()["items"] if item["name"] == payload["name"]]
    assert second_matches == first_matches

    listed = client.get("/api/wishlist")
    assert listed.status_code == 200
    listed_matches = [item for item in listed.json()["items"] if item["name"] == payload["name"]]
    assert listed_matches == first_matches


def test_wishlist_item_can_update_price_and_method_independently(client):
    created = client.post("/api/wishlist", json={"name": "سماعة لاسلكية", "price": 800, "method": "cash"})
    item = next(entry for entry in created.json()["items"] if entry["name"] == "سماعة لاسلكية")

    price_update = client.patch(f"/api/wishlist/{item['id']}", json={"price": 1600})
    assert price_update.status_code == 200
    updated = next(entry for entry in price_update.json()["items"] if entry["id"] == item["id"])
    assert updated["price"] == 1600
    assert updated["method"] == "cash"

    method_update = client.patch(f"/api/wishlist/{item['id']}", json={"method": "fin12"})
    assert method_update.status_code == 200
    updated = next(entry for entry in method_update.json()["items"] if entry["id"] == item["id"])
    assert updated["price"] == 1600
    assert updated["method"] == "fin12"
    assert "status" in updated and "when_label" in updated

    listed = client.get("/api/wishlist")
    listed_item = next(entry for entry in listed.json()["items"] if entry["id"] == item["id"])
    assert listed_item["price"] == 1600
    assert listed_item["method"] == "fin12"
    assert listed_item["status"] == updated["status"]


def test_wishlist_item_cannot_be_deleted_by_another_user(client):
    created = client.post("/api/wishlist", json={"name": "جهاز لوحي", "price": 1800, "method": "fin12"})
    item = next(item for item in created.json()["items"] if item["name"] == "جهاز لوحي")

    other_user_hash = main.security.hash_id("wishlist-other-user")
    with main.db.tx() as con:
        con.execute(
            "INSERT INTO users(user_hash, display_name) VALUES (?, ?)",
            (other_user_hash, "other"),
        )
        other_id = con.execute("SELECT id FROM users WHERE user_hash=?", (other_user_hash,)).fetchone()["id"]
        con.execute("INSERT INTO consents VALUES (?,?,?,?,?,?,?)",
                    ("other-consent", other_id, "demo1", "[]", "active", "2026-01-01", "2099-01-01"))
    other_user_token = main.security.sign_token({"sub": other_user_hash, "mode": "demo"})
    other_user_headers = {"Authorization": f"Bearer {other_user_token}"}

    response = client.delete(f"/api/wishlist/{item['id']}", headers=other_user_headers)
    assert response.status_code == 200
    assert response.json()["items"] == []

    still_owned = client.get("/api/wishlist")
    assert still_owned.status_code == 200
    assert any(entry["id"] == item["id"] for entry in still_owned.json()["items"])


def test_wishlist_item_cannot_be_updated_by_another_user(client):
    created = client.post("/api/wishlist", json={"name": "جهاز لوحي", "price": 1800, "method": "fin12"})
    item = next(entry for entry in created.json()["items"] if entry["name"] == "جهاز لوحي")

    other_user_hash = main.security.hash_id("wishlist-edit-other-user")
    with main.db.tx() as con:
        con.execute(
            "INSERT INTO users(user_hash, display_name) VALUES (?, ?)",
            (other_user_hash, "other"),
        )
    other_user_token = main.security.sign_token({"sub": other_user_hash, "mode": "demo"})
    other_user_headers = {"Authorization": f"Bearer {other_user_token}"}

    response = client.patch(
        f"/api/wishlist/{item['id']}",
        json={"price": 1, "method": "cash"},
        headers=other_user_headers,
    )
    assert response.status_code == 404

    still_owned = client.get("/api/wishlist")
    unchanged = next(entry for entry in still_owned.json()["items"] if entry["id"] == item["id"])
    assert unchanged["price"] == 1800
    assert unchanged["method"] == "fin12"


def test_bad_input_rejected(client):
    assert client.post("/api/scenarios", json={"price": -5}).status_code == 422
    wishlist_item = client.get("/api/wishlist").json()["items"][0]
    assert client.patch(f"/api/wishlist/{wishlist_item['id']}", json={}).status_code == 422
    assert client.patch(f"/api/wishlist/{wishlist_item['id']}", json={"price": -5}).status_code == 422
    assert client.patch(f"/api/wishlist/{wishlist_item['id']}", json={"method": "lease"}).status_code == 422
    assert client.get("/api/summary", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_demo_reset_still_works(client):
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json()["plans_found"] == 4


def test_production_requires_auth_and_disables_demo_routes(client, monkeypatch):
    monkeypatch.setattr(main, "PRODUCTION_MODE", True)
    monkeypatch.setattr(main, "DEMO_MODE", False)

    assert client.get("/api/summary").status_code == 401
    assert client.post("/api/consent", json={"bank_id": "demo1"}).status_code == 404
    assert client.post("/api/demo/reset").status_code == 404

    user_hash = main.security.hash_id("production-test-user")
    with main.db.tx() as con:
        con.execute("INSERT INTO users(user_hash, display_name) VALUES (?, ?)", (user_hash, "test"))
    token = main.security.sign_token({"sub": user_hash, "mode": "production"})
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/api/wishlist", headers=headers).status_code == 200
    assert client.post("/api/demo/next-month", headers=headers).status_code == 404


def _production_import(extra_env=None, code="import main"):
    env = os.environ.copy()
    for name in ("MAWID_ENV", "DEMO_MODE", "HMAC_KEY", "SIGNING_SECRET", "ALLOWED_ORIGINS"):
        env.pop(name, None)
    env.update({"MAWID_ENV": "production"})
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=os.path.dirname(os.path.dirname(__file__)),
        env=env,
        capture_output=True,
        text=True,
    )


def test_production_requires_configured_secrets():
    result = _production_import({"SIGNING_SECRET": "s" * 40})
    assert result.returncode != 0
    assert "HMAC_KEY is required" in result.stderr


def test_production_rejects_reused_secrets():
    secret = "s" * 40
    result = _production_import({
        "HMAC_KEY": secret,
        "SIGNING_SECRET": secret,
        "ALLOWED_ORIGINS": "https://mawid.example",
    })
    assert result.returncode != 0
    assert "must be different" in result.stderr


def test_production_requires_exact_https_cors_origins():
    secret_one, secret_two = "h" * 40, "s" * 40
    missing = _production_import({
        "HMAC_KEY": secret_one,
        "SIGNING_SECRET": secret_two,
    })
    assert missing.returncode != 0
    assert "ALLOWED_ORIGINS is required" in missing.stderr

    configured = _production_import(
        {
            "HMAC_KEY": secret_one,
            "SIGNING_SECRET": secret_two,
            "ALLOWED_ORIGINS": "https://app.mawid.example, https://admin.mawid.example/",
        },
        code="import main, json; print(json.dumps(main.app.user_middleware[0].kwargs['allow_origins']))",
    )
    assert configured.returncode == 0, configured.stderr
    assert json.loads(configured.stdout.strip()) == [
        "https://app.mawid.example",
        "https://admin.mawid.example",
    ]

    wildcard = _production_import({
        "HMAC_KEY": secret_one,
        "SIGNING_SECRET": secret_two,
        "ALLOWED_ORIGINS": "https://app.mawid.example, *",
    })
    assert wildcard.returncode != 0
    assert "exact HTTPS origins" in wildcard.stderr


def test_root_serves_frontend(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert 'text/html' in response.headers["content-type"]
    assert 'lang="ar" dir="rtl"' in response.text
    assert 'id="view"' in response.text and "/static/app.js" in response.text


def test_frontend_assets_and_api_docs(client):
    manifest = client.get("/static/manifest.json")
    assert manifest.status_code == 200
    assert manifest.json()["start_url"] == "/"
    for icon in manifest.json()["icons"]:
        response = client.get(icon["src"])
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
    assert client.get("/docs").status_code == 200

def test_expense_audit_contains_no_raw_financial_details(client):
    item = client.post("/api/expenses", json=_expense_payload(client)).json()["expense"]
    assert client.delete(f"/api/expenses/{item['id']}").status_code == 200
    with main.db.tx() as con:
        rows = con.execute(
            "SELECT action, detail FROM audit_log WHERE action LIKE 'expense.%' ORDER BY id"
        ).fetchall()
    assert [r["action"] for r in rows] == ["expense.added", "expense.deleted"]
    assert all(json.loads(r["detail"]) == {} for r in rows)

def test_expense_schema_upgrade_preserves_existing_bank_records(client):
    before = client.get("/api/summary").json()
    bank_rows = client.get("/api/expenses").json()["items"]
    with main.db.tx() as con:
        con.execute("DROP TABLE manual_expenses")
    main.db.init()
    main.db.init()
    assert client.get("/api/summary").json() == before
    assert client.get("/api/expenses").json()["items"] == bank_rows
    assert client.post("/api/expenses", json=_expense_payload(client)).status_code == 201

def test_expenses_use_salary_cycles_not_calendar_months(client):
    from datetime import date, timedelta
    import engine
    before = client.get("/api/summary").json()
    current = engine.cycle_index(date.fromisoformat(before["today"]), before["salary"]["day"])
    start = engine.cycle_start(current, before["salary"]["day"])
    old = client.post("/api/expenses", json=_expense_payload(
        client, date=(start - timedelta(days=1)).isoformat(), merchant="GROCERY",
        amount=100, description="SALARY PAYROLL",
    ))
    assert old.status_code == 201
    # Historical manual entries must not enter bank-based essentials or salary detection.
    assert client.get("/api/summary").json() == before
    assert old.json()["expense"] in client.get("/api/expenses").json()["items"]
    first_day = client.post("/api/expenses", json=_expense_payload(client, date=start.isoformat(), amount=20))
    assert first_day.status_code == 201
    assert client.get("/api/summary").json()["spent"] == before["spent"] + 20
    client.post("/api/demo/next-month")
    assert client.get("/api/summary").json()["spent"] == 0
    assert first_day.json()["expense"] in client.get("/api/expenses").json()["items"]

def test_expense_merge_keeps_legacy_entries_out_of_bank_calibration(client):
    before = client.get("/api/summary").json()
    with main.db.tx() as con:
        user_id = con.execute("SELECT id FROM users LIMIT 1").fetchone()["id"]
        con.execute(
            "INSERT INTO transactions(user_id,date,amount,direction,merchant,description,category,source) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, "2026-08-01", 999, "debit", "PANDA", "MANUAL",
             "essential:بقالة", "manual"),
        )
    assert client.get("/api/summary").json() == before
    legacy = next(r for r in client.get("/api/expenses").json()["items"]
                  if r["source"] == "manual")
    assert legacy["id"].startswith("legacy:") and legacy["deletable"]
    assert client.delete(f"/api/expenses/{legacy['id']}").status_code == 200
    assert client.get("/api/summary").json() == before


def test_expense_merge_registers_one_route_per_operation(client):
    for method in ("GET", "POST", "DELETE"):
        routes = [r for r in main.app.routes if getattr(r, "path", "").startswith("/api/expenses")
                  and method in getattr(r, "methods", set())]
        assert len(routes) == 1
    response = client.post("/api/expenses", json={
        "name": "قهوة", "amount": 20.001, "category": "flexible:مطاعم ومقاهي",
    })
    assert response.status_code == 422


def test_expense_endpoints_preserve_production_auth(client, monkeypatch):
    monkeypatch.setattr(main, "PRODUCTION_MODE", True)
    monkeypatch.setattr(main, "DEMO_MODE", False)
    payload = {"amount": 10, "merchant": "مقهى", "category": "flexible:مطاعم ومقاهي"}
    for method, path, kwargs in [
        ("get", "/api/expenses", {}),
        ("post", "/api/expenses", {"json": payload}),
        ("delete", "/api/expenses/manual:missing", {}),
    ]:
        assert getattr(client, method)(path, **kwargs).status_code == 401
        assert getattr(client, method)(path, headers={"Authorization": "Bearer forged.token"}, **kwargs).status_code == 401
        demo_token = main.security.sign_token({"sub": main.security.hash_id(main.DEMO_USER), "mode": "demo"})
        assert getattr(client, method)(path, headers={"Authorization": f"Bearer {demo_token}"}, **kwargs).status_code == 401
    user_hash = main.security.hash_id("production-expense-user")
    with main.db.tx() as con:
        con.execute("INSERT INTO users(user_hash) VALUES (?)", (user_hash,))
    headers = {"Authorization": "Bearer " + main.security.sign_token({"sub": user_hash, "mode": "production"})}
    response = client.post("/api/expenses", json=payload, headers=headers)
    assert response.status_code == 201
    item = response.json()["expense"]
    assert client.get("/api/expenses", headers=headers).json()["items"] == [item]
    assert client.delete(f"/api/expenses/{item['id']}", headers=headers).status_code == 200

def test_bank_transactions_are_read_only(client):
    before = client.get("/api/summary").json()
    bank_rows = client.get("/api/expenses").json()["items"]
    assert client.delete(f"/api/expenses/{bank_rows[0]['id']}").status_code == 404
    # Even a caller passing a bank's bare numeric ID cannot delete it.
    assert client.delete(f"/api/expenses/{bank_rows[0]['id'].split(':')[1]}").status_code == 404
    assert client.get("/api/expenses").json()["items"] == bank_rows
    assert client.get("/api/summary").json() == before

def test_expenses_are_isolated_between_users(client):
    item = client.post("/api/expenses", json=_expense_payload(client)).json()["expense"]
    owner_before = client.get("/api/summary").json()
    user_hash = main.security.hash_id("other-expense-user")
    with main.db.tx() as con:
        main.service.connect_bank(con, user_hash, "demo1")
    headers = {"Authorization": "Bearer " + main.security.sign_token({"sub": user_hash, "mode": "demo"})}
    other_before = client.get("/api/summary", headers=headers).json()
    other_rows = client.get("/api/expenses", headers=headers).json()["items"]
    assert item not in other_rows
    assert client.delete(f"/api/expenses/{item['id']}", headers=headers).status_code == 404
    assert client.get("/api/summary", headers=headers).json() == other_before
    other_item = client.post("/api/expenses", headers=headers, json=_expense_payload(client)).json()["expense"]
    assert other_item["id"] != item["id"]
    assert client.get("/api/summary").json() == owner_before
    assert other_item not in client.get("/api/expenses").json()["items"]
    assert client.delete(f"/api/expenses/{other_item['id']}").status_code == 404
    assert client.delete(f"/api/expenses/{other_item['id']}", headers=headers).status_code == 200
    assert client.get("/api/summary", headers=headers).json() == other_before

def test_category_correction_does_not_reclassify_manual_expenses(client):
    item = client.post("/api/expenses", json=_expense_payload(client, merchant="GROCERY")).json()["expense"]
    client.post("/api/categories", json={"merchant": "GROCERY", "category": "essential:بقالة"})
    assert next(r for r in client.get("/api/expenses").json()["items"] if r["id"] == item["id"]) == item
    assert client.get("/api/summary").json()["spent"] == pytest.approx(455.75)

def test_demo_reset_and_revocation_clear_manual_expenses(client):
    client.post("/api/expenses", json=_expense_payload(client))
    assert client.post("/api/demo/reset").status_code == 200
    assert all(r["source"] == "bank" for r in client.get("/api/expenses").json()["items"])
    client.post("/api/expenses", json=_expense_payload(client))
    assert client.delete("/api/consent").status_code == 200
    assert client.get("/api/expenses").json()["items"] == []

@pytest.mark.parametrize("amount", [0.01, 1_000_000])
def test_expense_amount_boundaries_and_default_account_date(client, amount):
    before = client.get("/api/summary").json()
    response = client.post("/api/expenses", json={
        "amount": amount, "merchant": "مطعم", "category": "flexible:أخرى",
    })
    assert response.status_code == 201
    assert response.json()["expense"]["date"] == before["today"]
    after = client.get("/api/summary").json()
    assert after["spent"] == pytest.approx(before["spent"] + amount)
    assert after["available"] == pytest.approx(before["available"] - amount)

@pytest.mark.parametrize("changes", [
    {"amount": 0}, {"amount": -1}, {"amount": 1_000_000.01}, {"amount": 1.001},
    {"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "-Infinity"}, {"amount": None},
    {"merchant": ""}, {"merchant": " \t "}, {"merchant": "a" * 81},
    {"description": "a" * 201}, {"category": "essential:بقالة"},
    {"category": "flexible:unknown"}, {"category": "income"}, {"category": ""},
    {"date": "invalid"}, {"date": "2026-02-30"}, {"date": "9999-12-31"},
    {"user_id": 999}, {"direction": "credit"}, {"source": "bank"},
])
def test_invalid_expenses_are_rejected_without_side_effects(client, changes):
    before = client.get("/api/summary").json()
    rows = client.get("/api/expenses").json()["items"]
    assert client.post("/api/expenses", json=_expense_payload(client, **changes)).status_code == 422
    assert client.get("/api/expenses").json()["items"] == rows
    assert client.get("/api/summary").json() == before

def test_manual_expense_updates_balance_categories_and_can_be_deleted(client):
    before = client.get("/api/summary").json()
    bank_rows = client.get("/api/expenses").json()["items"]
    assert bank_rows and all(r["source"] == "bank" and not r["deletable"] for r in bank_rows)
    response = client.post("/api/expenses", json=_expense_payload(client, merchant="  مقهى  "))
    assert response.status_code == 201
    item = response.json()["expense"]
    assert item["merchant"] == "مقهى"
    assert item["source"] == "manual" and item["deletable"]
    after = client.get("/api/summary").json()
    assert after["spent"] == pytest.approx(before["spent"] + 35.75)
    assert after["available"] == pytest.approx(before["available"] - 35.75)
    assert after["categories"]["flexible"]["مطاعم ومقاهي"] == pytest.approx(
        before["categories"]["flexible"].get("مطاعم ومقاهي", 0) + 35.75)
    assert after["formula"] == before["formula"]
    assert after["salary"] == before["salary"]
    assert after["categories"]["essentials"] == before["categories"]["essentials"]
    rows = client.get("/api/expenses").json()["items"]
    assert next(r for r in rows if r["id"] == item["id"]) == item
    assert [r for r in rows if r["source"] == "bank"] == bank_rows
    assert [r["date"] for r in rows] == sorted((r["date"] for r in rows), reverse=True)

    assert client.delete(f"/api/expenses/{item['id']}").status_code == 200
    assert client.get("/api/summary").json() == before
    assert client.get("/api/expenses").json()["items"] == bank_rows
    assert client.delete(f"/api/expenses/{item['id']}").status_code == 404
    assert client.delete("/api/expenses/missing").status_code == 404
