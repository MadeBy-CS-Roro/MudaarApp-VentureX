"""
Passwordless sign-up / log-in with a one-time code sent to the phone.

DEMO mode: no SMS is sent; the code is returned as `demo_code` so the demo can show it.
PRODUCTION: returns 501 until an SMS provider is configured. Never returns the code.
Raw phone numbers are never stored: only an HMAC hash and the last 3 digits.
"""
from __future__ import annotations
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

import security

CODE_TTL = timedelta(minutes=5)
LOCK_TIME = timedelta(minutes=15)
MAX_ATTEMPTS = 5
DEMO_PHONE = "+966500000123"


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", (raw or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")))
    if digits.startswith("00966"):
        digits = digits[5:]
    elif digits.startswith("966"):
        digits = digits[3:]
    if digits.startswith("05"):
        digits = digits[1:]
    if len(digits) == 9 and digits.startswith("5"):
        return "+966" + digits
    return None


def phone_hash(phone: str) -> str:
    return security.hash_id("phone:" + phone)


def user_hash_for(phone: str) -> str:
    return security.hash_id("user:" + phone)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _code_hash(phone_h: str, code: str) -> str:
    return security.hash_id(f"otp:{phone_h}:{code}")


def _issue(con, phone_h: str, purpose: str, name: str | None = None, email: str | None = None) -> str:
    row = con.execute("SELECT locked_until FROM otp_codes WHERE phone_hash=?", (phone_h,)).fetchone()
    if row and row["locked_until"] and row["locked_until"] > _now().isoformat():
        raise HTTPException(429, "جرّب بعد 15 دقيقة.")
    code = f"{secrets.randbelow(10**6):06d}"
    con.execute(
        "INSERT INTO otp_codes(phone_hash,code_hash,purpose,pending_name,pending_email,expires_at,attempts,locked_until) "
        "VALUES (?,?,?,?,?,?,0,NULL) ON CONFLICT(phone_hash) DO UPDATE SET code_hash=excluded.code_hash, "
        "purpose=excluded.purpose, pending_name=excluded.pending_name, pending_email=excluded.pending_email, "
        "expires_at=excluded.expires_at, attempts=0, locked_until=NULL",
        (phone_h, _code_hash(phone_h, code), purpose, name, email, (_now() + CODE_TTL).isoformat()))
    return code


def signup(con, name: str, phone_raw: str, email: str | None, demo_mode: bool) -> dict:
    phone = normalize_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.")
    if not demo_mode:
        raise HTTPException(501, "إرسال الرسائل يحتاج مزود SMS.")
    ph = phone_hash(phone)
    if con.execute("SELECT 1 FROM users WHERE phone_hash=?", (ph,)).fetchone():
        raise HTTPException(409, "الرقم مسجل، سجّل دخول.")
    code = _issue(con, ph, "signup", name.strip(), (email or "").strip() or None)
    return {"sent": True, "message": "أرسلنا لك رمز التحقق.", "demo_code": code}


def login(con, phone_raw: str, demo_mode: bool) -> dict:
    phone = normalize_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.")
    if not demo_mode:
        raise HTTPException(501, "إرسال الرسائل يحتاج مزود SMS.")
    ph = phone_hash(phone)
    out = {"sent": True, "message": "إذا الرقم مسجل بيوصلك رمز."}
    if con.execute("SELECT 1 FROM users WHERE phone_hash=?", (ph,)).fetchone():
        out["demo_code"] = _issue(con, ph, "login")
    return out


def verify(con, phone_raw: str, code: str) -> dict:
    phone = normalize_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.")
    ph = phone_hash(phone)
    row = con.execute("SELECT * FROM otp_codes WHERE phone_hash=?", (ph,)).fetchone()
    now = _now().isoformat()
    if not row:
        raise HTTPException(400, "اطلب رمز جديد.")
    if row["locked_until"] and row["locked_until"] > now:
        raise HTTPException(429, "جرّب بعد 15 دقيقة.")
    if row["expires_at"] <= now:
        raise HTTPException(400, "انتهى الرمز، اطلب واحد جديد.")
    if not hmac.compare_digest(row["code_hash"], _code_hash(ph, (code or "").strip())):
        attempts = row["attempts"] + 1
        locked = (_now() + LOCK_TIME).isoformat() if attempts >= MAX_ATTEMPTS else None
        con.execute("UPDATE otp_codes SET attempts=?, locked_until=? WHERE phone_hash=?", (attempts, locked, ph))
        con.commit()
        raise HTTPException(429 if locked else 400, "جرّب بعد 15 دقيقة." if locked else "الرمز غلط.")
    con.execute("DELETE FROM otp_codes WHERE phone_hash=?", (ph,))
    user = con.execute("SELECT * FROM users WHERE phone_hash=?", (ph,)).fetchone()
    if not user:
        if row["purpose"] != "signup":
            raise HTTPException(400, "اطلب رمز جديد.")
        con.execute("INSERT INTO users(user_hash, display_name, phone_hash, phone_last3, email) VALUES (?,?,?,?,?)",
                    (user_hash_for(phone), row["pending_name"], ph, phone[-3:], row["pending_email"]))
        user = con.execute("SELECT * FROM users WHERE phone_hash=?", (ph,)).fetchone()
    return session(con, user)


def session(con, user) -> dict:
    connected = bool(con.execute("SELECT 1 FROM consents WHERE user_id=? AND status='active'", (user["id"],)).fetchone())
    mode = "production" if security.PRODUCTION_MODE else "demo"
    token = security.sign_token({"sub": user["user_hash"], "mode": mode})
    return {"token": token, "name": user["display_name"], "bank_connected": connected}


def ensure_demo_user(con, demo_user_hash: str) -> object:
    """The quick-login persona (Noura). Same identity the tests and demo data use."""
    ph = phone_hash(DEMO_PHONE)
    con.execute("INSERT OR IGNORE INTO users(user_hash, display_name) VALUES (?,?)", (demo_user_hash, "نورة"))
    con.execute("UPDATE users SET phone_hash=COALESCE(phone_hash,?), phone_last3=COALESCE(phone_last3,'123'), "
                "email=COALESCE(email,'noura@example.com') WHERE user_hash=?", (ph, demo_user_hash))
    return con.execute("SELECT * FROM users WHERE user_hash=?", (demo_user_hash,)).fetchone()


# ---------- editing personal info ----------
def change_phone_start(con, user_id: int, phone_raw: str, demo_mode: bool) -> dict:
    phone = normalize_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.")
    if not demo_mode:
        raise HTTPException(501, "إرسال الرسائل يحتاج مزود SMS.")
    ph = phone_hash(phone)
    owner = con.execute("SELECT id FROM users WHERE phone_hash=?", (ph,)).fetchone()
    if owner and owner["id"] != user_id:
        raise HTTPException(409, "هالرقم مسجل بحساب ثاني.")
    code = _issue(con, ph, f"change:{user_id}")
    return {"sent": True, "message": "أرسلنا رمز للرقم الجديد.", "demo_code": code}


def change_phone_verify(con, user_id: int, phone_raw: str, code: str) -> dict:
    phone = normalize_phone(phone_raw)
    if not phone:
        raise HTTPException(422, "اكتب رقم جوال سعودي صحيح يبدأ بـ 05.")
    ph = phone_hash(phone)
    row = con.execute("SELECT * FROM otp_codes WHERE phone_hash=?", (ph,)).fetchone()
    now = _now().isoformat()
    if not row or row["purpose"] != f"change:{user_id}":
        raise HTTPException(400, "اطلب رمز جديد.")
    if row["locked_until"] and row["locked_until"] > now:
        raise HTTPException(429, "جرّب بعد 15 دقيقة.")
    if row["expires_at"] <= now:
        raise HTTPException(400, "انتهى الرمز، اطلب واحد جديد.")
    if not hmac.compare_digest(row["code_hash"], _code_hash(ph, (code or "").strip())):
        attempts = row["attempts"] + 1
        locked = (_now() + LOCK_TIME).isoformat() if attempts >= MAX_ATTEMPTS else None
        con.execute("UPDATE otp_codes SET attempts=?, locked_until=? WHERE phone_hash=?", (attempts, locked, ph))
        con.commit()
        raise HTTPException(429 if locked else 400, "جرّب بعد 15 دقيقة." if locked else "الرمز غلط.")
    con.execute("DELETE FROM otp_codes WHERE phone_hash=?", (ph,))
    con.execute("UPDATE users SET phone_hash=?, phone_last3=? WHERE id=?", (ph, phone[-3:], user_id))
    return {"ok": True, "phone_masked": f"05XX XXX {phone[-3:]}"}


# ---------- quick demo: every visitor gets a private copy ----------
GUEST_TTL_HOURS = 24
GUEST_TABLES = ("consents", "transactions", "manual_expenses", "plans", "wishlist", "demo_state", "category_overrides",
                "pending_actions", "chat_usage", "cycle_payments", "savings_deposits", "plan_settlements", "user_preferences", "score_events")


def new_demo_guest(con, connect_bank) -> object:
    import uuid
    user_hash = security.hash_id("demo-guest:" + uuid.uuid4().hex)
    con.execute("INSERT INTO users(user_hash, display_name, phone_last3, email, is_demo_guest) VALUES (?,?,?,?,1)",
                (user_hash, "نورة", "123", "noura@example.com"))
    connect_bank(con, user_hash, "demo1")
    return con.execute("SELECT * FROM users WHERE user_hash=?", (user_hash,)).fetchone()


def cleanup_demo_guests(con) -> int:
    import assistant

    cutoff = (_now() - timedelta(hours=GUEST_TTL_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
    ids = [r["id"] for r in con.execute(
        "SELECT id FROM users WHERE is_demo_guest=1 AND phone_hash IS NULL AND created_at < ?", (cutoff,))]
    for uid in ids:
        for table in GUEST_TABLES:
            con.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
        # SQLite may reuse this numeric ID for the next visitor. Remove all
        # process-local context before deleting the account that owns it.
        assistant.clear_user_context(uid)
        con.execute("DELETE FROM users WHERE id=?", (uid,))
    return len(ids)
