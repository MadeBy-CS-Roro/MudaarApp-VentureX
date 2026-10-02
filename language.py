"""Shared Saudi Arabic wording and number agreement."""

FORMS = {
    "payments": {"one": "دفعة وحدة", "two": "دفعتين", "few": "{n} دفعات", "many": "{n} دفعة"},
    "days": {"one": "يوم واحد", "two": "يومين", "few": "{n} أيام", "many": "{n} يوم"},
}


def counted(n: int, kind: str = "payments") -> str:
    forms = FORMS[kind]
    key = "one" if n == 1 else "two" if n == 2 else "few" if 3 <= n <= 10 else "many"
    return forms[key].replace("{n}", str(n))