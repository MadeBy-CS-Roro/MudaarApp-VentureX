"""Durable, validated, expiring and single-use assistant write proposals."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pydantic import ValidationError

import db
import inputs
import language
import service

WRITE_MODELS = {
    "add_expense": inputs.ExpenseIn,
    "add_obligation": inputs.PlanIn,
    "update_plan": inputs.UpdatePlanIn,
    "delete_obligation": inputs.DeletePlanIn,
    "add_to_wishlist": inputs.WishIn,
    "remove_from_wishlist": inputs.DeleteWishIn,
    "set_category": inputs.CategoryIn,
}


def validate(tool: str, params: dict) -> dict:
    if tool not in WRITE_MODELS:
        raise ValueError("الأداة مو متاحة.")
    try:
        out = WRITE_MODELS[tool](**params).model_dump()
    except (ValidationError, TypeError) as exc:
        raise ValueError("تأكد من البيانات قبل ما نكمل.") from exc
    if tool == "update_plan" and out["amount"] is None and out["remaining"] is None:
        raise ValueError("حدد المبلغ أو عدد الدفعات.")
    return out


def summary(con, user_id: int, tool: str, p: dict) -> str:
    if tool == "add_expense":
        return f"نضيف مصروف «{p['name']}» بـ {p['amount']:g} ر.س، بتصنيف {p['category'].split(':', 1)[1]}؟"
    if tool == "add_obligation":
        count = f"، باقي {language.counted(p['remaining'])}" if p["remaining"] is not None else "، التزام مستمر"
        return f"نضيف «{p['name']}» بـ {p['amount']:g} ر.س، يوم {p['day']}{count}؟"
    if tool in ("update_plan", "delete_obligation"):
        row = con.execute("SELECT name FROM plans WHERE user_id=? AND id=?", (user_id, p["plan_id"])).fetchone()
        if not row:
            raise ValueError("الالتزام مو موجود.")
        if tool == "delete_obligation":
            return f"نحذف التزام «{row['name']}» من موعد؟ هذا ما يلغي الدين عند الجهة."
        changes = []
        if p["amount"] is not None:
            changes.append(f"المبلغ {p['amount']:g} ر.س")
        if p["remaining"] is not None:
            changes.append(f"باقي {language.counted(p['remaining'])}" if p["remaining"] else "كل الدفعات تسدّدت")
        return f"نعدّل «{row['name']}»: {'، '.join(changes)}؟"
    if tool == "add_to_wishlist":
        methods = {"cash": "كاش", "bnpl3": "3 دفعات", "bnpl4": "4 دفعات", "bnpl6": "6 شهور",
                   "fin12": "تمويل 12 شهر", "save": "تجمع أول"}
        return f"نحط «{p['name']}» بـ {p['price']:g} ر.س بالأمنيات، بطريقة {methods[p['method']]}؟"
    if tool == "remove_from_wishlist":
        row = con.execute("SELECT name FROM wishlist WHERE user_id=? AND id=?", (user_id, p["item_id"])).fetchone()
        if not row:
            raise ValueError("الأمنية مو موجودة.")
        return f"نشيل «{row['name']}» من الأمنيات؟"
    return f"نعدّل تصنيف كل عمليات «{p['merchant']}» إلى {p['category'].split(':', 1)[1]}؟"


def propose(con, user_id: int, tool: str, params: dict) -> dict:
    p = validate(tool, params)
    text = summary(con, user_id, tool, p)
    now = datetime.now(timezone.utc)
    action = {"id": uuid.uuid4().hex, "tool": tool, "summary": text,
              "created_at": now.isoformat(), "expires_at": (now + timedelta(minutes=10)).isoformat(),
              "status": "pending"}
    con.execute("INSERT INTO pending_actions(id,user_id,tool,params,summary,created_at,expires_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (action["id"], user_id, tool, json.dumps(p, ensure_ascii=False), text,
                 action["created_at"], action["expires_at"]))
    return action


def apply(con, user_id: int, tool: str, p: dict) -> None:
    if tool == "add_expense":
        service.add_expense(con, user_id, **p)
    elif tool == "add_obligation":
        service.add_plan(con, user_id, **p)
    elif tool == "update_plan":
        if not service.confirm_plan(con, user_id, p["plan_id"], p["amount"], p["remaining"]):
            raise HTTPException(404, "الالتزام مو موجود.")
    elif tool == "delete_obligation":
        if not service.delete_plan(con, user_id, p["plan_id"]):
            raise HTTPException(404, "الالتزام مو موجود.")
    elif tool == "add_to_wishlist":
        service.add_wish(con, user_id, **p)
    elif tool == "remove_from_wishlist":
        if not remove_wish(con, user_id, p["item_id"]):
            raise HTTPException(404, "الأمنية مو موجودة.")
    elif tool == "set_category":
        service.set_category(con, user_id, **p)


def remove_wish(con, user_id: int, item_id: int) -> bool:
    return con.execute("DELETE FROM wishlist WHERE id=? AND user_id=?", (item_id, user_id)).rowcount > 0


def resolve(con, user: dict, action_id: str, confirm: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    status = "confirmed" if confirm else "cancelled"
    # First statement is a conditional write: acquires the SQLite write lock and
    # claims the action atomically. All service mutations and audit share this tx.
    claimed = con.execute("UPDATE pending_actions SET status=? WHERE id=? AND user_id=? "
                          "AND status='pending' AND expires_at>?",
                          (status, action_id, user["id"], now)).rowcount
    if not claimed:
        row = con.execute("SELECT * FROM pending_actions WHERE id=? AND user_id=?",
                          (action_id, user["id"])).fetchone()
        if not row:
            raise HTTPException(404, "الطلب مو موجود.")
        raise HTTPException(409, "الطلب انتهى أو تأكد أو انلغى قبل كذا.")
    row = con.execute("SELECT * FROM pending_actions WHERE id=?", (action_id,)).fetchone()
    if confirm:
        apply(con, user["id"], row["tool"], validate(row["tool"], json.loads(row["params"])))
    db.audit(con, user["hash"], f"chat.action.{status}", {"id": action_id, "tool": row["tool"]})
    return {"ok": True, "status": status}