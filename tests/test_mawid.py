"""Run: pytest -q   (uses a temporary database)"""
import os
import sys

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


def test_summary_numbers(client):
    s = client.get("/api/summary").json()
    assert s["formula"] == {"salary": 8700, "obligations": 4100, "essentials": 3500, "buffer": 500}
    assert s["safe_to_spend"] == 600 and s["spent"] == 420 and s["available"] == 180
    before = [a for a in s["alerts"] if a["type"] == "before_salary"][0]
    assert before["amount"] == 600 and before["plans"][0]["name"] == "تمارا"
    assert any(a["type"] == "plan_ending" and a["name"] == "تابي" for a in s["alerts"])


def test_scenarios(client):
    r = client.post("/api/scenarios", json={"price": 3000}).json()
    assert r["bnpl4"]["tight"] == -570 and r["bnpl4"]["earliest"] == 1
    assert r["fin12"]["total"] == 3300
    assert r["cash"]["earliest"] is None
    assert r["save"]["buyK"] == 3


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


def test_bad_input_rejected(client):
    assert client.post("/api/scenarios", json={"price": -5}).status_code == 422
    assert client.get("/api/summary", headers={"Authorization": "Bearer forged.token"}).status_code == 401


def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"
