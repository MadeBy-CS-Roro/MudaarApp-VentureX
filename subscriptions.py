"""Server-owned entitlements. UI visibility is never the access control."""
from fastapi import HTTPException

TIERS = (
    {"id": "basic", "name": "الأساسية", "price": 0, "obligation_limit": 5,
     "smart_account": False, "planner": False, "forecast": False},
    {"id": "plus", "name": "بلس", "price": 29, "obligation_limit": 30,
     "smart_account": True, "planner": True, "forecast": False},
    {"id": "premium", "name": "بريميوم", "price": 79, "obligation_limit": None,
     "smart_account": True, "planner": True, "forecast": True},
)


def current(con, user_id):
    row = con.execute("SELECT plan FROM user_preferences WHERE user_id=?", (user_id,)).fetchone()
    plan = row["plan"] if row else "basic"
    return dict(next(t for t in TIERS if t["id"] == plan))


def entitlements(con, user_id):
    tier = current(con, user_id)
    return {"plan": tier["id"], **{key: tier[key] for key in
            ("obligation_limit", "smart_account", "planner", "forecast")}}


def require(con, user_id, feature):
    if not current(con, user_id)[feature]:
        labels = {"smart_account": "الحساب الذكي", "planner": "محاكاة الالتزامات المحدثة",
                  "forecast": "محاكاة التوقعات المالية"}
        raise HTTPException(403, f"{labels[feature]} مو ضمن باقتك الحالية. ترقّ عشان تستخدمه.")


def cap(con, user_id, rows):
    limit = current(con, user_id)["obligation_limit"]
    visible = rows if limit is None else rows[:limit]
    hidden = len(rows) - len(visible)
    return {"items": visible, "limit": limit, "hidden_count": hidden,
            "locked_message": f"ترقّ عشان تشوف {hidden} التزامات" if hidden else None}


def check_plan_access(con, user_id, plan_id):
    limit = current(con, user_id)["obligation_limit"]
    if limit is None:
        return
    # Same order as plans_view. Historical completed plans remain accessible.
    from service import snapshot
    cur = snapshot(con, user_id).current
    rows = con.execute("SELECT id,active_until FROM plans WHERE user_id=? ORDER BY amount DESC,id",
                       (user_id,)).fetchall()
    active = [row["id"] for row in rows if row["active_until"] is None or row["active_until"] >= cur]
    if plan_id in active[limit:]:
        raise HTTPException(403, "هالالتزام خارج حد باقتك. ترقّ عشان تشوفه وتعدّله.")


def check_creation(con, user_id):
    limit = current(con, user_id)["obligation_limit"]
    if limit is None:
        return
    from service import obligations_view
    count = obligations_view(con, user_id)["total_count"]
    if count >= limit:
        raise HTTPException(403, f"باقتك تسمح بـ {limit} التزامات. ترقّ عشان تضيف التزام ثاني.")


def response(con, user_id, demo_mode):
    tiers = []
    for item in TIERS:
        tier = dict(item)
        tier["features"] = [
            "التزامات بلا حد" if tier["obligation_limit"] is None else f"{tier['obligation_limit']} التزامات",
            "الحساب الذكي" if tier["smart_account"] else "بدون الحساب الذكي",
            "محاكاة الالتزامات المحدثة" if tier["planner"] else "بدون محاكاة الالتزامات المحدثة",
            "محاكاة التوقعات المالية للعميل" if tier["forecast"] else "بدون محاكاة التوقعات المالية",
        ]
        tiers.append(tier)
    return {"current": current(con, user_id), "tiers": tiers, "demo_mode": demo_mode}


def switch_demo(con, user_id, plan):
    con.execute("INSERT INTO user_preferences(user_id,plan) VALUES (?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan", (user_id, plan))