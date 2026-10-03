"""Guest expiry must discard private context before SQLite can reuse an ID."""
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pytest

import assistant
import auth
import db
import service


@pytest.fixture
def guest_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "guest-cleanup.db"))
    monkeypatch.setattr(assistant, "_history", defaultdict(lambda: deque(maxlen=10)))
    monkeypatch.setattr(
        assistant, "_last",
        defaultdict(lambda: {"price": 3000.0, "method": "bnpl4", "name": "جوال"}),
    )
    monkeypatch.setattr(assistant, "API_KEY", None)
    db.init()
    with db.tx() as con:
        yield con


def seed_context(uid):
    assistant._history[uid].append({"role": "user", "content": "synthetic old visitor chat"})
    assistant._last[uid].update({"price": 98765.0, "method": "save", "name": "synthetic old purchase"})


def test_expired_guest_deletion_clears_both_caches_before_id_reuse(guest_db, monkeypatch):
    con = guest_db
    old = auth.new_demo_guest(con, service.connect_bank)
    uid = old["id"]
    seed_context(uid)
    con.execute("UPDATE users SET created_at='2020-01-01 00:00:00' WHERE id=?", (uid,))
    assert con.execute("SELECT COUNT(*) FROM transactions WHERE user_id=?", (uid,)).fetchone()[0] > 0
    assert auth.cleanup_demo_guests(con) == 1
    assert con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone() is None
    for table in auth.GUEST_TABLES:
        assert con.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (uid,)).fetchone()[0] == 0
    assert uid not in assistant._history
    assert uid not in assistant._last
    assert auth.cleanup_demo_guests(con) == 0
    # Intentionally exercise SQLite's INTEGER PRIMARY KEY reuse, not merely
    # two different user IDs with independently populated context.
    new = auth.new_demo_guest(con, service.connect_bank)
    assert new["id"] == uid
    assert new["user_hash"] != old["user_hash"]
    assert assistant._last[uid] == {"price": 3000.0, "method": "bnpl4", "name": "جوال"}

    sent_messages = []

    class Reply:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"type": "text", "text": "synthetic fresh reply"}]}

    def fake_post(*args, **kwargs):
        sent_messages.extend(kwargs["json"]["messages"])
        return Reply()

    monkeypatch.setattr(assistant, "API_KEY", "synthetic-test-key")
    monkeypatch.setattr(assistant.httpx, "post", fake_post)
    assert assistant.chat(con, uid, "synthetic fresh question")["mode"] == "llm"
    assert sent_messages == [{"role": "user", "content": "synthetic fresh question"}]
    assert list(assistant._history[uid]) == [
        {"role": "user", "content": "synthetic fresh question"},
        {"role": "assistant", "content": "synthetic fresh reply"},
    ]


def test_cleanup_protects_fresh_boundary_and_phone_registered_accounts(guest_db, monkeypatch):
    con = guest_db
    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(auth, "_now", lambda: now)
    fresh = auth.new_demo_guest(con, service.connect_bank)
    boundary = auth.new_demo_guest(con, service.connect_bank)
    registered_guest = auth.new_demo_guest(con, service.connect_bank)
    registered = auth.new_demo_guest(con, service.connect_bank)
    expired = auth.new_demo_guest(con, service.connect_bank)
    con.execute("UPDATE users SET created_at=?", (now.strftime("%Y-%m-%d %H:%M:%S"),))
    con.execute("UPDATE users SET created_at=? WHERE id=?",
                ((now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S"), boundary["id"]))
    for user in (registered_guest, registered, expired):
        con.execute("UPDATE users SET created_at='2020-01-01 00:00:00' WHERE id=?", (user["id"],))
    # A guest that adds a phone retains its demo flag in the existing app.
    con.execute("UPDATE users SET phone_hash='synthetic-phone-a' WHERE id=?", (registered_guest["id"],))
    con.execute("UPDATE users SET phone_hash='synthetic-phone-b', is_demo_guest=0 WHERE id=?", (registered["id"],))
    protected = (fresh, boundary, registered_guest, registered)
    for user in (*protected, expired):
        seed_context(user["id"])
    rows_before = {
        user["id"]: {
            table: [tuple(row) for row in con.execute(f"SELECT * FROM {table} WHERE user_id=?", (user["id"],))]
            for table in auth.GUEST_TABLES
        } for user in protected
    }
    assert auth.cleanup_demo_guests(con) == 1
    assert expired["id"] not in assistant._history
    assert expired["id"] not in assistant._last
    for user in protected:
        uid = user["id"]
        assert con.execute("SELECT 1 FROM users WHERE id=?", (uid,)).fetchone()
        assert list(assistant._history[uid]) == [{"role": "user", "content": "synthetic old visitor chat"}]
        assert assistant._last[uid]["price"] == 98765.0
        for table in auth.GUEST_TABLES:
            assert [tuple(row) for row in con.execute(f"SELECT * FROM {table} WHERE user_id=?", (uid,))] == rows_before[uid][table]


def test_expired_guest_without_cached_context_is_safe_to_clean(guest_db):
    guest = auth.new_demo_guest(guest_db, service.connect_bank)
    guest_db.execute("UPDATE users SET created_at='2020-01-01 00:00:00' WHERE id=?", (guest["id"],))
    assert auth.cleanup_demo_guests(guest_db) == 1
    assert not assistant._history
    assert not assistant._last