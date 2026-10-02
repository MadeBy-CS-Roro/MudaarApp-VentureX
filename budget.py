"""Per-user budget targets and actual current-cycle distribution."""
import engine as E

DEFAULTS = {"essentials_pct": 70, "personal_pct": 20, "savings_pct": 10}


def targets(con, user_id):
    row = con.execute("SELECT essentials_pct,personal_pct,savings_pct FROM user_preferences WHERE user_id=?",
                      (user_id,)).fetchone()
    return dict(row) if row else dict(DEFAULTS)


def update(con, user_id, values):
    con.execute("INSERT INTO user_preferences(user_id,essentials_pct,personal_pct,savings_pct) VALUES (?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET essentials_pct=excluded.essentials_pct,"
                "personal_pct=excluded.personal_pct,savings_pct=excluded.savings_pct",
                (user_id, values["essentials_pct"], values["personal_pct"], values["savings_pct"]))


def view(con, user_id, s):
    goal = targets(con, user_id)
    saved = con.execute("SELECT COALESCE(SUM(amount),0) FROM savings_deposits WHERE user_id=? AND cycle=?",
                        (user_id, s.current)).fetchone()[0]
    values = E.budget_distribution(s, goal, saved)
    values["targets"] = goal
    values["note"] = "المتبقي يشمل هامش الأمان. الادخار يوضح الإيداعات المسجلة هالشهر، مو مجموع الأمنيات."
    return values