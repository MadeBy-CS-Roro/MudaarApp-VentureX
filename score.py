"""
Money-management score (0-100) and points.

FAIR BY DESIGN: every part is measured against the user's OWN situation (their salary, their own
targets, what was actually possible this month) — never against an amount. Someone on 6,000 SAR and
someone on 30,000 SAR can both reach 100. The standings rank this score, never balances or spending.
"""
from __future__ import annotations
from datetime import datetime, timezone

import budget
import engine as E

PARTS = (  # id, label, max points
    ("on_time", "سداد الالتزامات بوقتها", 25),
    ("personal", "الالتزام بحد صرفك الشخصي", 20),
    ("essentials", "الالتزامات مقابل هدفك من الراتب", 15),
    ("debt", "نسبة الديون من راتبك", 15),
    ("savings", "التحويش حسب قدرتك", 15),
    ("subscriptions", "متابعة الاشتراكات", 10),
)
GRADES = ((85, "ممتاز"), (70, "جيد جداً"), (55, "جيد"), (0, "يحتاج شغل"))

# Sample competitors for the demo standings (nicknames only, no money data).
DEMO_RIVALS = (("صقر الميزانية", 94), ("أبو حساب", 91), ("منظمة", 88), ("الهادئ", 86), ("رايق", 84),
               ("قطرة قطرة", 82), ("ميزان", 79), ("خطوة خطوة", 77), ("بدر", 74), ("مرتّبة", 72),
               ("متفائل", 68), ("الحالم", 63), ("بادئ", 58), ("يتعلم", 51))


def _lin(value, good, bad, maximum):
    """maximum points at `good` or better, 0 at `bad`, straight line between."""
    if good == bad:
        return maximum
    t = (value - good) / (bad - good)
    return round(maximum * (1 - max(0.0, min(1.0, t))), 1)


def compute(con, user_id: int) -> dict:
    import service
    s = service.summary(con, user_id)
    snap = service.snapshot(con, user_id)
    salary = s["formula"]["salary"] or 1
    goal = budget.targets(con, user_id)
    parts = []

    # 1. on time: anything late this month costs points; payments still ahead are fine.
    o = service.obligations_view(con, user_id)
    late = sum(1 for i in o["active_items"] if i["status"] == "late")
    pts = max(0, 25 - 10 * late)
    parts.append(("on_time", pts, "ما عليك ولا دفعة متأخرة." if not late else f"عندك {late} دفعة متأخرة، سدّدها ترجع لك النقاط.",
                  None if not late else "ادفع المتأخر من «ادفع الكل» أو من موقع الجهة."))

    # 2. personal spending: pace against YOUR limit for the days passed, and not going below zero.
    cap = goal["personal_pct"] / 100 * salary
    start = E.cycle_start(snap.current, snap.profile.salary_day)
    nxt = E.cycle_start(snap.current + 1, snap.profile.salary_day)
    passed = max(1, (snap.extra["today"] - start).days + 1) / max(1, (nxt - start).days)
    pace = s["spent"] / max(1.0, cap * passed)
    pts = _lin(pace, 1.0, 2.0, 10) + (10 if s["available"] >= 0 else _lin(-s["available"], 0, max(1.0, s["safe_to_spend"]), 10))
    parts.append(("personal", pts, "صرفك الشخصي ماشي على حدك." if pace <= 1 and s["available"] >= 0 else "صرفك أسرع من حدك هالشهر.",
                  None if pts >= 19 else f"خلك تحت {round(cap):,} ر.س شخصي هالشهر، وما تتعدى «باقي لك»."))

    # 3. commitments vs YOUR essentials target.
    share = s["obligations_total"] / salary * 100
    over = share - goal["essentials_pct"]
    pts = _lin(over, 0, 30, 15)
    parts.append(("essentials", pts, f"التزاماتك {round(share)}% من راتبك وهدفك {goal['essentials_pct']}%.",
                  None if over <= 0 else "قلّل التزام أو اشتراك، أو لا تضيف التزام جديد لين تنزل النسبة."))

    # 4. debt burden (installments and loans only).
    debt = sum(p["amount"] for p in s["plans"] if p.get("kind") in ("bnpl", "loan"))
    dbr = debt / salary * 100
    pts = _lin(dbr, 20, 45, 15)
    parts.append(("debt", pts, f"ديونك {round(dbr)}% من راتبك.",
                  None if dbr <= 20 else "كل التزام يخلص يرفع نقاطك. تجنّب أقساط جديدة لين تنزل تحت 20%."))

    # 5. savings: judged on what was POSSIBLE for you, so tight months aren't punished.
    target = min(goal["savings_pct"] / 100 * salary, max(0.0, s["safe_to_spend"]))
    last = con.execute("SELECT COALESCE(SUM(amount),0) FROM savings_deposits WHERE user_id=? AND cycle=?",
                       (user_id, snap.current - 1)).fetchone()[0]
    has_history = con.execute("SELECT 1 FROM score_events WHERE user_id=? AND kind='month_closed'", (user_id,)).fetchone()
    if target <= 0:
        pts, note = 15, "ما كان فيه مجال للتحويش، وما ننقص عليك."
    elif not has_history:
        pts, note = 7, "أول شهر لك، نقاط التحويش تكتمل لما يخلص الشهر."
    else:
        pts, note = round(15 * min(1.0, last / target), 1), f"حوّشت {round(last):,} ر.س الشهر اللي فات من {round(target):,} ممكنة."
    parts.append(("savings", pts, note, None if pts >= 15 else f"حوّش {round(target):,} ر.س هالشهر (من «تجمع أول») وتاخذ النقاط كاملة."))

    # 6. subscriptions: reminders on, and acting on the ones you planned to cancel.
    subs = [p for p in service.plans_view(con, user_id) if p["kind"] == "subscription" and (p["remaining"] is None or p["remaining"] > 0)]
    no_reminder = sum(1 for p in subs if not p["remind"])
    pending_cancel = sum(1 for p in subs if p["cancel_planned"])
    pts = max(0, 10 - 3 * no_reminder - 2 * pending_cancel)
    parts.append(("subscriptions", pts, "اشتراكاتك تحت السيطرة." if pts == 10 else "فيه اشتراكات تحتاج متابعة.",
                  None if pts == 10 else "شغّل التذكير، وألغِ اللي ناوي تلغيه قبل التجديد."))

    labels = {p[0]: (p[1], p[2]) for p in PARTS}
    out = [{"id": pid, "label": labels[pid][0], "points": round(pt), "max": labels[pid][1], "note": note, "tip": tip}
           for pid, pt, note, tip in parts]
    total = min(100, sum(p["points"] for p in out))
    bonus = con.execute("SELECT COALESCE(SUM(points),0) FROM score_events WHERE user_id=?", (user_id,)).fetchone()[0]
    grade = next(label for floor, label in GRADES if total >= floor)
    return {"score": total, "grade": grade, "parts": out, "points": int(total + bonus),
            "bonus": int(bonus), "fair_note": "النقاط تُحسب على وضعك أنت وأهدافك، مو على كبر راتبك."}


def award(con, user_id: int, kind: str, points: int, ref: str) -> None:
    con.execute("INSERT OR IGNORE INTO score_events(user_id,kind,points,ref,created_at) VALUES (?,?,?,?,?)",
                (user_id, kind, points, ref, datetime.now(timezone.utc).isoformat()))


def events(con, user_id: int, limit: int = 8) -> list[dict]:
    rows = con.execute("SELECT kind, points, created_at FROM score_events WHERE user_id=? ORDER BY id DESC LIMIT ?",
                       (user_id, limit)).fetchall()
    names = {"paid_early": "دفعت التزام قبل موعده", "sub_cancelled": "ألغيت اشتراك ما تحتاجه",
             "plan_confirmed": "أكدت التزام", "month_closed": "خلّصت شهر", "under_limit": "خلّصت الشهر تحت حدك الشخصي"}
    return [{"label": names.get(r["kind"], r["kind"]), "points": r["points"]} for r in rows]


def leaderboard(con, user_id: int, demo_mode: bool) -> dict:
    me = compute(con, user_id)
    pref = con.execute("SELECT leaderboard_opt_in, leaderboard_name, display_name FROM users WHERE id=?",
                       (user_id,)).fetchone()
    rows = [{"name": n, "score": sc, "me": False} for n, sc in (DEMO_RIVALS if demo_mode else ())]
    others = con.execute("SELECT id, leaderboard_name FROM users WHERE leaderboard_opt_in=1 AND id<>? LIMIT 50",
                         (user_id,)).fetchall()
    for r in others:
        try:
            rows.append({"name": r["leaderboard_name"] or "مستخدم", "score": compute(con, r["id"])["score"], "me": False})
        except Exception:
            continue
    my_name = pref["leaderboard_name"] or "أنت"
    rows.append({"name": my_name, "score": me["score"], "me": True})
    rows.sort(key=lambda x: (-x["score"], not x["me"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    mine = next(r for r in rows if r["me"])
    return {"rank": mine["rank"], "total": len(rows), "score": me["score"], "points": me["points"],
            "opt_in": bool(pref["leaderboard_opt_in"]), "nickname": pref["leaderboard_name"],
            "rows": rows[:20] if mine["rank"] <= 20 else rows[:19] + [mine],
            "note": "الترتيب على حسن إدارتك لفلوسك نسبةً لوضعك، مو على كبر الراتب. ما نعرض أي مبالغ، الاسم المستعار والنقاط بس."}


def set_public(con, user_id: int, opt_in: bool, nickname: str | None) -> None:
    con.execute("UPDATE users SET leaderboard_opt_in=?, leaderboard_name=? WHERE id=?",
                (int(opt_in), (nickname or "").strip() or None, user_id))
