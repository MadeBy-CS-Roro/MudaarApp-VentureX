"""Private quick-login personas and bounded guest lifetime."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import main
from test_mudar_auth_payments import app_client, demo, h, signup


def identity(headers):
    body = main.security.verify_token(headers["Authorization"].removeprefix("Bearer "))
    with main.db.tx() as con:
        return dict(con.execute("SELECT * FROM users WHERE user_hash=?", (body["sub"],)).fetchone())


def test_demo_guests_are_private_and_reset_only_their_own_copy(app_client):
    a, b = demo(app_client), demo(app_client)
    ua, ub = identity(a), identity(b)
    assert ua["id"] != ub["id"] and ua["user_hash"] != ub["user_hash"]
    for user, headers in ((ua, a), (ub, b)):
        assert user["is_demo_guest"] == 1 and user["phone_hash"] is None
        assert (user["display_name"], user["phone_last3"], user["email"]) == ("نورة", "123", "noura@example.com")
        assert app_client.get("/api/auth/me", headers=headers).json()["bank_connected"] is True
        assert app_client.get("/api/summary", headers=headers).json()["available"] == 180
    assert app_client.post("/api/wishlist", headers=a,
                           json={"name": "خاص بالزائر الأول", "price": 1000, "method": "save"}).status_code == 200
    assert not any(w["name"] == "خاص بالزائر الأول"
                   for w in app_client.get("/api/wishlist", headers=b).json()["items"])
    assert app_client.post("/api/payments/pay", headers=a, json={"item_ids": ["tamara"]}).status_code == 200
    assert app_client.get("/api/payments/due", headers=a).json()["payable_total"] == 0
    assert app_client.get("/api/payments/due", headers=b).json()["payable_total"] == 600
    app_client.post("/api/banks", headers=b, json={"bank_id": "demo2"})
    assert len(app_client.get("/api/banks", headers=a).json()["banks"]) == 1
    app_client.post("/api/demo/next-month", headers=b)
    other_before = app_client.get("/api/summary", headers=b).json()
    assert app_client.post("/api/demo/reset", headers=a).status_code == 200
    assert app_client.get("/api/payments/due", headers=a).json()["payable_total"] == 600
    assert app_client.get("/api/summary", headers=a).json()["available"] == 180
    assert app_client.get("/api/summary", headers=b).json() == other_before
    assert app_client.get("/api/auth/me", headers=a).status_code == 200


def test_cleanup_removes_all_expired_guest_rows_and_protects_phone_users(app_client):
    expired, fresh = identity(demo(app_client)), identity(demo(app_client))
    registered = identity(h(signup(app_client)["token"]))
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    uid = expired["id"]
    main.assistant._history[uid] = [{"role": "user", "content": "expired guest"}]
    main.assistant._last[uid] = {"name": "expired guest"}
    tables = ("consents", "transactions", "manual_expenses", "plans", "wishlist",
              "demo_state", "category_overrides", "pending_actions", "chat_usage",
              "cycle_payments", "savings_deposits", "plan_settlements", "user_preferences")
    with main.db.tx() as con:
        con.execute("UPDATE users SET created_at=? WHERE id=?", (past, uid))
        # Even an incorrectly flagged phone account must never be deleted.
        con.execute("UPDATE users SET created_at=?,is_demo_guest=1 WHERE id=?", (past, registered["id"]))
        con.execute("INSERT INTO users(user_hash,created_at) VALUES ('legacy-demo',?)", (past,))
        con.execute("INSERT INTO manual_expenses(id,user_id,date,amount,merchant,category) "
                    "VALUES ('expired-expense',?,'2026-10-01',20,'TEST','flexible:أخرى')", (uid,))
        con.execute("INSERT INTO category_overrides VALUES (?,'TEST','flexible:أخرى')", (uid,))
        con.execute("INSERT INTO pending_actions(id,user_id,tool,params,summary,created_at,expires_at) "
                    "VALUES ('expired-action',?,'add_expense','{}','test',?,?)", (uid, past, past))
        con.execute("INSERT INTO chat_usage VALUES (?,0,1)", (uid,))
        con.execute("INSERT INTO cycle_payments VALUES (?,'tamara',0,600,?,'demo')", (uid, past))
        wish_id = con.execute("SELECT id FROM wishlist WHERE user_id=?", (uid,)).fetchone()[0]
        con.execute("INSERT INTO savings_deposits(user_id,cycle,amount,wish_id) VALUES (?,0,20,?)", (uid, wish_id))
        con.execute("INSERT INTO plan_settlements VALUES (?,'tamara',0,600,0,?,'test')", (uid, past))
        main.db.audit(con, expired["user_hash"], "test")
        assert all(con.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (uid,)).fetchone() for table in tables)
    assert main.db.cleanup_demo_guests() == 1
    assert main.db.cleanup_demo_guests() == 0
    assert uid not in main.assistant._history and uid not in main.assistant._last
    with main.db.tx() as con:
        assert not con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
        assert all(not con.execute(f"SELECT 1 FROM {table} WHERE user_id=?", (uid,)).fetchone() for table in tables)
        assert not con.execute("SELECT 1 FROM audit_log WHERE user_hash=?", (expired["user_hash"],)).fetchone()
        assert con.execute("SELECT 1 FROM users WHERE id=?", (fresh["id"],)).fetchone()
        assert con.execute("SELECT 1 FROM users WHERE id=?", (registered["id"],)).fetchone()
        assert con.execute("SELECT 1 FROM users WHERE user_hash='legacy-demo'").fetchone()
        assert not con.execute("PRAGMA foreign_key_check").fetchall()


def test_cleanup_runs_on_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(main.db, "DB_PATH", str(tmp_path / "startup.db"))
    monkeypatch.setattr(main, "DEMO_MODE", True)
    main.db.init()
    with main.db.tx() as con:
        con.execute("INSERT INTO users(user_hash,is_demo_guest,created_at) "
                    "VALUES ('expired-startup',1,datetime('now','-25 hours'))")
    with TestClient(main.app):
        with main.db.tx() as con:
            assert not con.execute("SELECT 1 FROM users WHERE user_hash='expired-startup'").fetchone()


def test_cleanup_is_scheduled_once_per_hour(monkeypatch):
    events = []

    async def sleep(seconds):
        events.append(("sleep", seconds))
        if len(events) == 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(main.db, "cleanup_demo_guests", lambda: events.append(("cleanup",)))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._hourly_guest_cleanup())
    assert events == [("sleep", 3600), ("cleanup",), ("sleep", 3600)]