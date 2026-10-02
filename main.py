"""
Mawid API (FastAPI).  Run:  uvicorn main:app --host 0.0.0.0 --port 8000
Docs at /docs.  Put your front end in ./static/index.html to serve it from /.
"""
from __future__ import annotations
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import assistant
import db
import detect
import security
import service

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"   # no token needed for the stage demo
DEMO_USER = "demo-noura"

@asynccontextmanager
async def lifespan(_app):
    db.init()
    yield

app = FastAPI(title="Mawid API", version="0.1", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
limiter = security.RateLimiter(limit=int(os.getenv("RATE_LIMIT", "120")), window=60)


# ---------- request models ----------
class ConsentIn(BaseModel):
    bank_id: str = Field(min_length=1, max_length=40)

class ConfirmIn(BaseModel):
    amount: Optional[float] = Field(default=None, gt=0, le=1_000_000)
    remaining: Optional[int] = Field(default=None, ge=0, le=600)

class PriceIn(BaseModel):
    price: float = Field(gt=0, le=1_000_000)

class WishIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    price: float = Field(gt=0, le=1_000_000)
    method: Literal["cash", "bnpl4", "fin12", "save"]

class CategoryIn(BaseModel):
    merchant: str = Field(min_length=1, max_length=80)
    category: str = Field(pattern=r"^(essential|flexible):.{1,30}$")

class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)


# ---------- auth + rate limit ----------
def current_user(request: Request, authorization: Optional[str] = Header(default=None)) -> dict:
    key = authorization or (request.client.host if request.client else "anon")
    if not limiter.allow(key):
        raise HTTPException(429, "طلبات كثيرة، جرب بعد دقيقة.")
    user_hash = None
    if authorization and authorization.startswith("Bearer "):
        body = security.verify_token(authorization[7:])
        if not body:
            raise HTTPException(401, "الجلسة انتهت، اربط حسابك من جديد.")
        user_hash = body["sub"]
    elif DEMO_MODE:
        user_hash = security.hash_id(DEMO_USER)
    else:
        raise HTTPException(401, "لازم تسجل دخول.")
    with db.tx() as con:
        row = con.execute("SELECT id FROM users WHERE user_hash=?", (user_hash,)).fetchone()
    if not row:
        raise HTTPException(404, "ما فيه حساب مربوط. ابدأ من POST /api/consent.")
    return {"id": row["id"], "hash": user_hash}


# ---------- routes ----------
@app.get("/api/health")
def health():
    return {"ok": True, "llm": bool(assistant.API_KEY), "demo_mode": DEMO_MODE}


@app.post("/api/consent")
def consent(body: ConsentIn, request: Request):
    if not limiter.allow(request.client.host if request.client else "anon"):
        raise HTTPException(429, "طلبات كثيرة، جرب بعد دقيقة.")
    user_hash = security.hash_id(DEMO_USER)   # production: hash of the bank's customer id
    with db.tx() as con:
        r = service.connect_bank(con, user_hash, body.bank_id)
        db.audit(con, user_hash, "consent.granted", {"bank": body.bank_id, "consent_id": r["consent_id"],
                                                     "plans_found": len(r["plans"])})
    token = security.sign_token({"sub": user_hash, "cid": r["consent_id"]})
    return {"consent_id": r["consent_id"], "token": token, "expires_at": r["expires_at"],
            "plans_found": len(r["plans"]), "unknown_merchants": r["unknown_merchants"]}


@app.delete("/api/consent")
def revoke(user=Depends(current_user)):
    with db.tx() as con:
        service.revoke(con, user["id"])
        db.audit(con, user["hash"], "consent.revoked")
    return {"ok": True}


@app.get("/api/plans")
def get_plans(user=Depends(current_user)):
    with db.tx() as con:
        return {"plans": service.plans_view(con, user["id"])}


@app.post("/api/plans/{plan_id}/confirm")
def confirm(plan_id: str, body: ConfirmIn, user=Depends(current_user)):
    with db.tx() as con:
        if not service.confirm_plan(con, user["id"], plan_id, body.amount, body.remaining):
            raise HTTPException(404, "الخطة غير موجودة.")
        db.audit(con, user["hash"], "plan.confirmed", {"plan": plan_id, "edited": body.amount is not None or body.remaining is not None})
        return {"ok": True, "plans": service.plans_view(con, user["id"])}


@app.get("/api/summary")
def get_summary(user=Depends(current_user)):
    with db.tx() as con:
        return service.summary(con, user["id"])


@app.post("/api/scenarios")
def post_scenarios(body: PriceIn, user=Depends(current_user)):
    with db.tx() as con:
        return service.scenarios(con, user["id"], body.price)


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


@app.delete("/api/wishlist/{item_id}")
def delete_wish(item_id: int, user=Depends(current_user)):
    with db.tx() as con:
        con.execute("DELETE FROM wishlist WHERE id=? AND user_id=?", (item_id, user["id"]))
        return {"items": service.wishlist(con, user["id"])}


@app.post("/api/categories")
def set_category(body: CategoryIn, user=Depends(current_user)):
    """User fixes a category once; we remember it for that merchant."""
    with db.tx() as con:
        con.execute("INSERT OR REPLACE INTO category_overrides VALUES (?,?,?)", (user["id"], body.merchant, body.category))
        con.execute("UPDATE transactions SET category=? WHERE user_id=? AND merchant=?", (body.category, user["id"], body.merchant))
        return {"ok": True}


@app.post("/api/chat")
def post_chat(body: ChatIn, user=Depends(current_user)):
    with db.tx() as con:
        r = assistant.chat(con, user["id"], body.message)
        db.audit(con, user["hash"], "chat", {"tools": r["tools"]})   # log tools used, not the message
        return r


@app.post("/api/demo/next-month")
def demo_next_month(user=Depends(current_user)):
    with db.tx() as con:
        r = service.next_month(con, user["id"])
        db.audit(con, user["hash"], "demo.next_month", {"events": len(r["events"])})
        return r


@app.post("/api/demo/reset")
def demo_reset(request: Request):
    return consent(ConsentIn(bank_id="demo1"), request)


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
