"""SQLite schema and small helpers."""
import json
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("MAWID_DB", "mawid.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  user_hash TEXT UNIQUE NOT NULL,          -- HMAC of the external id, never the raw id
  display_name TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS consents (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  bank_id TEXT NOT NULL,
  scopes TEXT NOT NULL,                    -- JSON list, read-only scopes
  status TEXT NOT NULL DEFAULT 'active',   -- active | revoked | expired
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL,
  amount REAL NOT NULL,                    -- positive number
  direction TEXT NOT NULL,                 -- debit | credit
  merchant TEXT NOT NULL,
  description TEXT,
  category TEXT,                           -- essential:<name> | flexible:<name> | installment | income | NULL
  source TEXT NOT NULL DEFAULT 'bank'
);
CREATE INDEX IF NOT EXISTS ix_tx_user_date ON transactions(user_id, date);
CREATE TABLE IF NOT EXISTS manual_expenses (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  date TEXT NOT NULL,
  amount REAL NOT NULL CHECK(amount > 0 AND amount <= 1000000),
  merchant TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL CHECK(category IN (
    'flexible:مطاعم', 'flexible:توصيل', 'flexible:تسوق',
    'flexible:ترفيه', 'flexible:أخرى'
  ))
);
CREATE INDEX IF NOT EXISTS ix_manual_user_date ON manual_expenses(user_id, date);
CREATE TABLE IF NOT EXISTS plans (
  id TEXT NOT NULL,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  merchant TEXT NOT NULL,
  kind TEXT NOT NULL,                      -- bnpl | loan | recurring
  amount REAL NOT NULL,
  day INTEGER NOT NULL,
  active_until INTEGER,                    -- last cycle index with a payment, NULL = recurring
  total_count INTEGER,
  confirmed INTEGER NOT NULL DEFAULT 0,
  action TEXT,                             -- JSON {kind,label,url|value}
  PRIMARY KEY (user_id, id)
);
CREATE TABLE IF NOT EXISTS category_overrides (
  user_id INTEGER NOT NULL, merchant TEXT NOT NULL, category TEXT NOT NULL,
  PRIMARY KEY (user_id, merchant)
);
CREATE TABLE IF NOT EXISTS wishlist (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  price REAL NOT NULL,
  method TEXT NOT NULL,                    -- cash | bnpl4 | fin12 | save
  saved REAL NOT NULL DEFAULT 0,
  notified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS demo_state (
  user_id INTEGER PRIMARY KEY, today TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY,
  ts TEXT DEFAULT CURRENT_TIMESTAMP,
  user_hash TEXT,
  action TEXT NOT NULL,
  detail TEXT                              -- JSON, never raw transactions
);
CREATE TABLE IF NOT EXISTS pending_actions (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  tool TEXT NOT NULL,
  params TEXT NOT NULL,
  summary TEXT NOT NULL,
  created_at TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS ix_action_user ON pending_actions(user_id, status);
CREATE TABLE IF NOT EXISTS contacts (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  message TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS chat_usage (
  user_id INTEGER NOT NULL REFERENCES users(id),
  cycle INTEGER NOT NULL,
  questions INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (user_id, cycle)
);
CREATE TABLE IF NOT EXISTS user_preferences (
  user_id INTEGER PRIMARY KEY REFERENCES users(id),
  essentials_pct INTEGER NOT NULL DEFAULT 70 CHECK(essentials_pct BETWEEN 0 AND 100),
  personal_pct INTEGER NOT NULL DEFAULT 20 CHECK(personal_pct BETWEEN 0 AND 100),
  savings_pct INTEGER NOT NULL DEFAULT 10 CHECK(savings_pct BETWEEN 0 AND 100),
  plan TEXT NOT NULL DEFAULT 'basic' CHECK(plan IN ('basic','plus','premium')),
  CHECK(essentials_pct+personal_pct+savings_pct=100)
);
CREATE TABLE IF NOT EXISTS savings_deposits (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  cycle INTEGER NOT NULL,
  amount REAL NOT NULL CHECK(amount>0),
  wish_id INTEGER REFERENCES wishlist(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS plan_settlements (
  user_id INTEGER NOT NULL REFERENCES users(id),
  plan_id TEXT NOT NULL,
  cycle INTEGER NOT NULL,
  amount REAL NOT NULL CHECK(amount>0),
  reserved_amount REAL NOT NULL DEFAULT 0,
  paid_at TEXT NOT NULL,
  plan_name TEXT NOT NULL,
  PRIMARY KEY(user_id,plan_id)
);
"""


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init():
    with tx() as con:
        con.executescript(SCHEMA)
        columns = {r["name"] for r in con.execute("PRAGMA table_info(transactions)")}
        if "source" not in columns:
            con.execute("ALTER TABLE transactions ADD COLUMN source TEXT NOT NULL DEFAULT 'bank'")
        if "reserved_amount" not in {r["name"] for r in con.execute("PRAGMA table_info(plan_settlements)")}:
            con.execute("ALTER TABLE plan_settlements ADD COLUMN reserved_amount REAL NOT NULL DEFAULT 0")
        # Only pre-existing demo users start Plus; production defaults Basic.
        con.execute("INSERT OR IGNORE INTO user_preferences(user_id,plan) "
                    "SELECT id,CASE WHEN EXISTS(SELECT 1 FROM demo_state WHERE user_id=users.id) "
                    "THEN 'plus' ELSE 'basic' END FROM users")


def audit(con, user_hash: str, action: str, detail: dict | None = None):
    con.execute("INSERT INTO audit_log(user_hash, action, detail) VALUES (?,?,?)",
                (user_hash, action, json.dumps(detail or {}, ensure_ascii=False)))
