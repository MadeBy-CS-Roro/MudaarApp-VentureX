"""Server-owned entitlements. UI visibility is never the access control."""
from fastapi import HTTPException

TIERS = (
    {"id": "basic", "name": "الأساسية", "price": 0, "obligation_limit": 5, "assistant_questions": 5,
     "smart_account": False, "planner": False, "forecast": False},
    {"id": "plus", "name": "بلس", "price": 29, "obligation_limit": 30, "assistant_questions": 30,
     "smart_account": True, "planner": True, "forecast": False},
    {"id": "premium", "name": "بريميوم", "price": 79, "obligation_limit": None, "assistant_questions": None,
     "smart_account": True, "planner": True, "forecast": True},
)

# What each plan INCLUDES. Plus and Premium list only what they add on top of the plan before.
INCLUDES = {
    "basic": ["لين 5 التزامات (أقساط، إيجار، اشتراكات)", "«تقدر تصرف» لهالشهر", "ربط أكثر من بنك",
              "تنبيه قبل الراتب وتذكير قبل تجديد الاشتراكات", "المصروفات مع التصنيف الذكي وحد الصرف الشخصي",
              "تتبع الالتزامات مقابل نسبتها من راتبك", "ادفع الكل", "قائمة الأمنيات مع «تجمع أول»", "المساعد الذكي: 5 أسئلة بالشهر"],
    "plus": ["لين 30 التزام", "الحساب الذكي: كم يبقى لك بالشهور الجاية ومتى تقدر تشتري",
             "المخطط: مقارنة التقسيط والتمويل وتجمع أول، واختيار الأنسب لك", "المساعد الذكي: 30 سؤال بالشهر"],
    "premium": ["التزامات بلا حد", "توقعاتك المالية لـ 12 شهر", "المساعد الذكي بلا حد"],
}


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


def active_commitments(con, user_id) -> int:
    """Commitments that count toward the plan limit: every plan with payments left (bills excluded)."""
    from service import plans_view
    return sum(1 for p in plans_view(con, user_id) if p["remaining"] is None or p["remaining"] > 0)


def limit_info(con, user_id, count: int | None = None) -> dict:
    tier = current(con, user_id)
    count = active_commitments(con, user_id) if count is None else count
    limit = tier["obligation_limit"]
    return {"limit": limit, "used": count, "left": None if limit is None else max(0, limit - count),
            "plan": tier["id"], "plan_name": tier["name"]}


def check_creation(con, user_id):
    limit = current(con, user_id)["obligation_limit"]
    if limit is None:
        return
    if active_commitments(con, user_id) >= limit:
        raise HTTPException(403, f"باقتك تسمح بـ {limit} التزامات. ترقّ عشان تضيف التزام ثاني.")


def check_question(con, user_id, cycle: int) -> bool:
    """Atomically count one assistant question against the plan's monthly allowance."""
    allowed = current(con, user_id)["assistant_questions"]
    if allowed is None:
        con.execute("INSERT INTO chat_usage(user_id,cycle,questions) VALUES (?,?,1) "
                    "ON CONFLICT(user_id,cycle) DO UPDATE SET questions=questions+1", (user_id, cycle))
        return True
    return con.execute("INSERT INTO chat_usage(user_id,cycle,questions) VALUES (?,?,1) "
                       "ON CONFLICT(user_id,cycle) DO UPDATE SET questions=questions+1 WHERE questions<?",
                       (user_id, cycle, allowed)).rowcount > 0


def response(con, user_id, demo_mode):
    tiers, previous = [], None
    for item in TIERS:
        tier = dict(item)
        tier["includes_previous"] = previous          # "everything in <previous>, plus:"
        tier["features"] = list(INCLUDES[tier["id"]])
        tiers.append(tier)
        previous = tier["name"]
    return {"current": current(con, user_id), "tiers": tiers, "demo_mode": demo_mode,
            "usage": limit_info(con, user_id)}


def switch_demo(con, user_id, plan):
    con.execute("INSERT INTO user_preferences(user_id,plan) VALUES (?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET plan=excluded.plan", (user_id, plan))