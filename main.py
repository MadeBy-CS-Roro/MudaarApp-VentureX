"""
Mudar (مُدار) API (FastAPI).  Run:  uvicorn main:app --host 0.0.0.0 --port 8000
Docs at /docs.  Put your front end in ./static/index.html to serve it from /.
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from datetime import date as Date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

import assistant
import db
import detect
import security
import service
import actions
import inputs
import language
import budget
import subscriptions
import auth
import payments

PRODUCTION_MODE = security.PRODUCTION_MODE
DEMO_MODE = not PRODUCTION_MODE
DEMO_USER = "demo-noura"
# Requests without a token act as the demo persona ONLY when this is set (used by the
# automated tests). The app itself always logs in and sends a token.
ALLOW_ANON = os.getenv("MUDAR_ALLOW_ANON", "").lower() in ("1", "true", "yes")


def _allowed_origins() -> list[str]:
    if not PRODUCTION_MODE:
        return ["*"]

    configured = os.getenv("ALLOWED_ORIGINS", "")
    if not configured.strip():
        raise RuntimeError("ALLOWED_ORIGINS is required in production.")

    origins = []
    for item in configured.split(","):
        origin = item.strip().rstrip("/")
        parsed = urlsplit(origin)
        try:
            parsed.port
        except ValueError as exc:
            raise RuntimeError("ALLOWED_ORIGINS must contain valid HTTPS origins.") from exc
        if (
            parsed.scheme.lower() != "https"
            or not parsed.hostname
            or "*" in parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeError("ALLOWED_ORIGINS must contain exact HTTPS origins without paths or wildcards.")
        origins.append(f"https://{parsed.netloc.lower()}")

    if not origins:
        raise RuntimeError("ALLOWED_ORIGINS must contain at least one origin.")
    return list(dict.fromkeys(origins))


@asynccontextmanager
async def lifespan(_app):
    db.init()
    yield

app = FastAPI(title="Mudar API", version="0.1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "PATCH", "DELETE"] if PRODUCTION_MODE else ["*"],
    allow_headers=["Authorization", "Content-Type"] if PRODUCTION_MODE else ["*"],
)
limiter = security.RateLimiter(limit=int(os.getenv("RATE_LIMIT", "120")), window=60)


# ---------- request models ----------
class ConsentIn(BaseModel):
    bank_id: str = Field(min_length=1, max_length=40)

class ConfirmIn(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    remaining: Optional[int] = Field(default=None, ge=0, le=600)

class PriceIn(BaseModel):
    price: float = Field(gt=0, le=1_000_000)

class OfferIn(PriceIn):
    target_months: Optional[int] = Field(default=None, ge=1, le=36, strict=True)

class BudgetIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    essentials_pct: int = Field(ge=0, le=100, strict=True)
    personal_pct: int = Field(ge=0, le=100, strict=True)
    savings_pct: int = Field(ge=0, le=100, strict=True)

class DemoSubscriptionIn(BaseModel):
    plan: Literal["basic", "plus", "premium"]

WishIn = inputs.WishIn

class WishUpdate(BaseModel):
    price: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    method: Optional[Literal["cash", "bnpl3", "bnpl4", "bnpl6", "fin12", "save"]] = None

class CategoryIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=80)
    category: str = Field(pattern=r"^(essential|flexible):.{1,30}$")

    @field_validator("category")
    @classmethod
    def known_category(cls, value):
        if value not in detect.ALL_CATEGORIES:
            raise ValueError("اختر تصنيف من القائمة.")
        return value

class ExpenseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(gt=0, le=1_000_000, max_digits=9, decimal_places=2)
    merchant: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)
    category: str

    @field_validator("category")
    @classmethod
    def personal_category(cls, value):
        if not value.startswith("flexible:") or value not in detect.ALL_CATEGORIES:
            raise ValueError("اختر تصنيف من القائمة.")
        return value
    date: Optional[Date] = None

    @field_validator("merchant", "description", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)

PlanIn = inputs.PlanIn
ContactIn = inputs.ContactIn
contact_limiter = security.RateLimiter(limit=5, window=60)


# ---------- auth + rate limit ----------
def _token_user_hash(authorization: Optional[str]) -> Optional[str]:
    if not (authorization and authorization.startswith("Bearer ")):
        return None
    body = security.verify_token(authorization[7:].strip())
    if not body or not isinstance(body.get("sub"), str) or not body["sub"]:
        raise HTTPException(401, "الجلسة انتهت، سجّل دخول من جديد.")
    if PRODUCTION_MODE and body.get("mode") != "production":
        raise HTTPException(401, "لازم تسجل دخول.")
    return body["sub"]


def _rate(request: Request, authorization: Optional[str]):
    key = authorization or (request.client.host if request.client else "anon")
    if not limiter.allow(key):
        raise HTTPException(429, "طلبات كثيرة، جرب بعد دقيقة.")


def signed_in_user(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    """Logged in (or demo anon in tests), bank connection NOT required."""
    _rate(request, authorization)
    user_hash = _token_user_hash(authorization)
    if user_hash is None:
        if DEMO_MODE and ALLOW_ANON:
            user_hash = security.hash_id(DEMO_USER)
        else:
            raise HTTPException(401, "لازم تسجل دخول.")
    with db.tx() as con:
        row = con.execute("SELECT id FROM users WHERE user_hash=?", (user_hash,)).fetchone()
    if not row:
        raise HTTPException(404, "اربط حسابك البنكي أول.")
    return {"id": row["id"], "hash": user_hash}


def current_user(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    """Logged-in user. The app checks /api/auth/me to send users without a bank to onboarding."""
    return signed_in_user(request, authorization)


# ---------- routes ----------
@app.get("/api/health")
def health():
    return {"ok": True, "llm": bool(assistant.API_KEY), "demo_mode": DEMO_MODE}


@app.get("/api/language")
def get_language():
    return language.FORMS


@app.post("/api/consent")
def consent(body: ConsentIn, request: Request, authorization: Optional[str] = Header(default=None)):
    if not DEMO_MODE:
        raise HTTPException(404, "المسار غير متاح.")
    if not limiter.allow(request.client.host if request.client else "anon"):
        raise HTTPException(429, "طلبات كثيرة، جرب بعد دقيقة.")
    user_hash = _token_user_hash(authorization)
    if user_hash is None:
        if not ALLOW_ANON:
            raise HTTPException(401, "لازم تسجل دخول.")
        user_hash = security.hash_id(DEMO_USER)
    with db.tx() as con:
        if user_hash == security.hash_id(DEMO_USER):
            auth.ensure_demo_user(con, user_hash)
        r = service.connect_bank(con, user_hash, body.bank_id)
        db.audit(con, user_hash, "consent.granted", {"bank": body.bank_id, "consent_id": r["consent_id"],
                                                     "plans_found": len(r["plans"])})
    token = security.sign_token({
        "sub": user_hash,
        "cid": r["consent_id"],
        "mode": "demo" if DEMO_MODE else "production",
    })
    assistant._history.pop(r["user_id"], None)
    assistant._last.pop(r["user_id"], None)
    return {"consent_id": r["consent_id"], "token": token, "expires_at": r["expires_at"],
            "plans_found": len(r["plans"]), "unknown_merchants": r["unknown_merchants"]}


# ---------- auth: phone + one-time code ----------
class SignupIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=2, max_length=40)
    phone: str = Field(min_length=9, max_length=20)
    email: Optional[str] = Field(default=None, max_length=120, pattern=r"^$|^[^@\s]+@[^@\s]+\.[^@\s]+$")
    accept_terms: bool

class PhoneIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    phone: str = Field(min_length=9, max_length=20)

class VerifyIn(PhoneIn):
    code: str = Field(min_length=4, max_length=8)

auth_ip_limiter = security.RateLimiter(limit=20, window=60)
auth_phone_limiter = security.RateLimiter(limit=5, window=60)


def _auth_rate(request: Request, phone: str):
    ip = request.client.host if request.client else "anon"
    if not auth_ip_limiter.allow(ip) or not auth_phone_limiter.allow(auth.normalize_phone(phone) or phone):
        raise HTTPException(429, "طلبات كثيرة، جرّب بعد دقيقة.")


def _auth_out(out: dict) -> dict:
    if not DEMO_MODE:
        out.pop("demo_code", None)   # never leak codes outside the demo
    return out


@app.post("/api/auth/signup")
def auth_signup(body: SignupIn, request: Request):
    _auth_rate(request, body.phone)
    if not body.accept_terms:
        raise HTTPException(422, "لازم توافق على الشروط وسياسة الخصوصية.")
    with db.tx() as con:
        return _auth_out(auth.signup(con, body.name, body.phone, body.email, DEMO_MODE))


@app.post("/api/auth/login")
def auth_login(body: PhoneIn, request: Request):
    _auth_rate(request, body.phone)
    with db.tx() as con:
        return _auth_out(auth.login(con, body.phone, DEMO_MODE))


@app.post("/api/auth/verify")
def auth_verify(body: VerifyIn, request: Request):
    _auth_rate(request, body.phone)
    with db.tx() as con:
        out = auth.verify(con, body.phone, body.code)
        db.audit(con, None, "auth.verified")
        return out


@app.post("/api/auth/demo")
def auth_demo(request: Request):
    """Quick login as Noura for the stage demo. Demo mode only."""
    if not DEMO_MODE:
        raise HTTPException(404, "المسار غير متاح.")
    if not limiter.allow(request.client.host if request.client else "anon"):
        raise HTTPException(429, "طلبات كثيرة، جرب بعد دقيقة.")
    user_hash = security.hash_id(DEMO_USER)
    with db.tx() as con:
        user = auth.ensure_demo_user(con, user_hash)
        if not con.execute("SELECT 1 FROM consents WHERE user_id=? AND status='active'", (user["id"],)).fetchone():
            service.connect_bank(con, user_hash, "demo1")
        return auth.session(con, user)


@app.get("/api/auth/me")
def auth_me(user=Depends(signed_in_user)):
    with db.tx() as con:
        row = con.execute("SELECT display_name FROM users WHERE id=?", (user["id"],)).fetchone()
        connected = bool(con.execute("SELECT 1 FROM consents WHERE user_id=? AND status='active'",
                                     (user["id"],)).fetchone())
    return {"name": row["display_name"], "bank_connected": connected}


@app.post("/api/auth/logout")
def auth_logout():
    # Tokens are stateless and short-lived; the app deletes its copy.
    return {"ok": True}


@app.delete("/api/consent")
def revoke(user=Depends(signed_in_user)):
    with db.tx() as con:
        service.revoke(con, user["id"])
        db.audit(con, user["hash"], "consent.revoked")
    assistant._history.pop(user["id"], None)
    assistant._last.pop(user["id"], None)
    return {"ok": True}


@app.get("/api/plans")
def get_plans(user=Depends(current_user)):
    with db.tx() as con:
        return service.visible_plans(con, user["id"])


@app.post("/api/plans/{plan_id}/confirm")
def confirm(plan_id: str, body: ConfirmIn, user=Depends(current_user)):
    with db.tx() as con:
        if not service.confirm_plan(con, user["id"], plan_id, body.amount, body.remaining):
            raise HTTPException(404, "الخطة غير موجودة.")
        db.audit(con, user["hash"], "plan.confirmed", {"plan": plan_id, "edited": body.amount is not None or body.remaining is not None})
        return {"ok": True, **service.visible_plans(con, user["id"])}


@app.post("/api/plans/{plan_id}/pay-all")
def pay_all(plan_id: str, user=Depends(current_user)):
    with db.tx() as con:
        try:
            result = service.pay_all(con, user["id"], plan_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        db.audit(con, user["hash"], "plan.settled", {"plan": plan_id, "already_paid": result["already_paid"]})
        return result


class PayModeIn(BaseModel):
    pay_mode: Literal["auto", "manual"]

class PayIn(BaseModel):
    item_ids: list[str] = Field(min_length=1, max_length=30)


@app.patch("/api/plans/{plan_id}")
def patch_plan(plan_id: str, body: PayModeIn, user=Depends(current_user)):
    with db.tx() as con:
        if not payments.set_mode(con, user["id"], plan_id, body.pay_mode):
            raise HTTPException(404, "الالتزام مو موجود.")
        db.audit(con, user["hash"], "plan.pay_mode", {"plan": plan_id, "mode": body.pay_mode})
        return payments.due(con, user["id"])


@app.get("/api/payments/due")
def get_payments_due(user=Depends(current_user)):
    with db.tx() as con:
        return payments.due(con, user["id"])


@app.post("/api/payments/pay")
def post_payments(body: PayIn, user=Depends(current_user)):
    with db.tx() as con:
        out = payments.pay(con, user["id"], body.item_ids, DEMO_MODE)
        db.audit(con, user["hash"], "payments.demo_paid", {"count": len(out["paid"]), "total": out["total"]})
        return {**out, "due": payments.due(con, user["id"])}


@app.get("/api/categories")
def get_categories():
    return {"groups": [{"id": "essential", "label": "الأساسيات", "items": detect.CATEGORIES["essential"]},
                       {"id": "flexible", "label": "شخصية", "items": detect.CATEGORIES["flexible"]}]}


@app.get("/api/summary")
def get_summary(user=Depends(current_user)):
    with db.tx() as con:
        return service.summary(con, user["id"])


@app.post("/api/scenarios")
def post_scenarios(body: PriceIn, user=Depends(current_user)):
    with db.tx() as con:
        return service.scenarios(con, user["id"], body.price)


@app.get("/api/expenses")
def get_expenses(user=Depends(current_user)):
    with db.tx() as con:
        return service.expense_overview(con, user["id"])


@app.post("/api/expenses", status_code=201)
def post_expense(body: ExpenseIn | inputs.ExpenseIn, response: Response, user=Depends(current_user)):
    with db.tx() as con:
        if isinstance(body, inputs.ExpenseIn):
            service.add_expense(con, user["id"], **body.model_dump())
            db.audit(con, user["hash"], "expense.added")
            response.status_code = 200
            return service.expense_overview(con, user["id"])
        try:
            item = service.add_expense(
                con, user["id"], float(body.amount), body.merchant, body.category,
                body.date, body.description,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        db.audit(con, user["hash"], "expense.added")
        return {"expense": item}


@app.delete("/api/expenses/{item_id}")
def delete_expense(item_id: str, user=Depends(current_user)):
    with db.tx() as con:
        if not service.delete_expense(con, user["id"], item_id):
            raise HTTPException(404, "المصروف اليدوي غير موجود.")
        db.audit(con, user["hash"], "expense.deleted")
        return {"ok": True}


@app.get("/api/wishlist")
def get_wishlist(user=Depends(current_user)):
    with db.tx() as con:
        return {"items": service.wishlist(con, user["id"])}


@app.post("/api/wishlist")
def post_wishlist(body: WishIn, user=Depends(current_user)):
    with db.tx() as con:
        service.add_wish(con, user["id"], body.name, body.price, body.method)
        db.audit(con, user["hash"], "wishlist.added", {"method": body.method})
        return {"items": service.wishlist(con, user["id"])}


@app.patch("/api/wishlist/{item_id}")
def patch_wishlist(item_id: int, body: WishUpdate, user=Depends(current_user)):
    updates = body.model_dump(exclude_unset=True)
    if not updates or any(value is None for value in updates.values()):
        raise HTTPException(422, "حدد السعر أو طريقة الشراء بقيمة صحيحة.")

    with db.tx() as con:
        if not service.update_wish(
            con, user["id"], item_id, updates.get("price"), updates.get("method")
        ):
            raise HTTPException(404, "العنصر غير موجود.")
        db.audit(con, user["hash"], "wishlist.updated", {"fields": sorted(updates)})
        return {"items": service.wishlist(con, user["id"])}


@app.delete("/api/wishlist/{item_id}")
def delete_wish(item_id: int, user=Depends(current_user)):
    with db.tx() as con:
        actions.remove_wish(con, user["id"], item_id)
        return {"items": service.wishlist(con, user["id"])}


@app.post("/api/categories")
def set_category(body: CategoryIn, user=Depends(current_user)):
    """User fixes a category once; we remember it for that merchant."""
    with db.tx() as con:
        service.set_category(con, user["id"], body.merchant, body.category)
        db.audit(con, user["hash"], "category.updated")
        return {"ok": True}


@app.get("/api/obligations")
def get_obligations(user=Depends(current_user)):
    with db.tx() as con:
        return service.obligations_view(con, user["id"])


@app.post("/api/plans")
def post_plan(body: PlanIn, user=Depends(current_user)):
    with db.tx() as con:
        pid = service.add_plan(con, user["id"], **body.model_dump())
        db.audit(con, user["hash"], "plan.added", {"plan": pid})
        return {"id": pid, **service.visible_plans(con, user["id"])}


@app.delete("/api/plans/{plan_id}")
def delete_plan(plan_id: str, user=Depends(current_user)):
    with db.tx() as con:
        if not service.delete_plan(con, user["id"], plan_id):
            raise HTTPException(404, "الالتزام مو موجود.")
        db.audit(con, user["hash"], "plan.deleted", {"plan": plan_id})
        return service.visible_plans(con, user["id"])


@app.post("/api/offers")
def post_offers(body: OfferIn, user=Depends(current_user)):
    with db.tx() as con:
        return service.offer_comparison(con, user["id"], body.price, body.target_months)


@app.get("/api/budget")
def get_budget(user=Depends(current_user)):
    with db.tx() as con:
        return budget.view(con, user["id"], service.snapshot(con, user["id"]))


@app.put("/api/budget")
def put_budget(body: BudgetIn, user=Depends(current_user)):
    values = body.model_dump()
    if sum(values.values()) != 100:
        raise HTTPException(422, "مجموع نسب توزيع راتبك لازم يكون 100%.")
    with db.tx() as con:
        budget.update(con, user["id"], values)
        db.audit(con, user["hash"], "budget.updated")
        return budget.view(con, user["id"], service.snapshot(con, user["id"]))


@app.get("/api/subscriptions")
def get_subscriptions(user=Depends(current_user)):
    with db.tx() as con:
        return subscriptions.response(con, user["id"], DEMO_MODE)


@app.post("/api/demo/subscription")
def demo_subscription(body: DemoSubscriptionIn, user=Depends(current_user)):
    if not DEMO_MODE:
        raise HTTPException(404, "المسار غير متاح.")
    with db.tx() as con:
        subscriptions.switch_demo(con, user["id"], body.plan)
        db.audit(con, user["hash"], "demo.subscription", {"plan": body.plan})
        return subscriptions.response(con, user["id"], True)


@app.get("/api/smart-account")
def get_smart_account(user=Depends(current_user)):
    with db.tx() as con:
        return service.smart_account(con, user["id"])


@app.get("/api/forecast")
def get_forecast(user=Depends(current_user)):
    with db.tx() as con:
        return service.financial_forecast(con, user["id"])


@app.get("/api/account")
def get_account(user=Depends(current_user)):
    with db.tx() as con:
        return service.account(con, user["id"], DEMO_MODE)


@app.post("/api/contact")
def post_contact(body: ContactIn, request: Request):
    if not contact_limiter.allow(request.client.host if request.client else "anon"):
        raise HTTPException(429, "طلبات كثيرة، جرّب بعد دقيقة.")
    with db.tx() as con:
        con.execute("INSERT INTO contacts(name,message) VALUES (?,?)", (body.name, body.message))
    return {"ok": True}


@app.post("/api/chat")
def post_chat(body: ChatIn, user=Depends(current_user)):
    # Commit the atomic quota claim before waiting for an external LLM.
    with db.tx() as con:
        if not service.consume_chat_question(con, user["id"]):
            raise HTTPException(429, "خلصت أسئلتك المجانية هالشهر. تتجدد الشهر الجاي، وباقي مزايا مُدار متاحة لك.")
    with db.tx() as con:
        r = assistant.chat(con, user["id"], body.message)
        db.audit(con, user["hash"], "chat", {"tools": r["tools"]})   # log tools used, not the message
        return r


@app.post("/api/chat/actions/{action_id}/confirm")
def confirm_chat_action(action_id: str, user=Depends(current_user)):
    with db.tx() as con:
        return actions.resolve(con, user, action_id, True)


@app.post("/api/chat/actions/{action_id}/cancel")
def cancel_chat_action(action_id: str, user=Depends(current_user)):
    with db.tx() as con:
        return actions.resolve(con, user, action_id, False)


@app.post("/api/demo/next-month")
def demo_next_month(user=Depends(current_user)):
    if not DEMO_MODE:
        raise HTTPException(404, "المسار غير متاح.")
    with db.tx() as con:
        r = service.next_month(con, user["id"])
        db.audit(con, user["hash"], "demo.next_month", {"events": len(r["events"])})
        return r


@app.post("/api/demo/reset")
def demo_reset(request: Request, authorization: Optional[str] = Header(default=None)):
    if not DEMO_MODE:
        raise HTTPException(404, "المسار غير متاح.")
    return consent(ConsentIn(bank_id="demo1"), request, authorization)


# ---------- optional: serve the front end ----------
STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def api_index():
        return RedirectResponse(url="/docs")
