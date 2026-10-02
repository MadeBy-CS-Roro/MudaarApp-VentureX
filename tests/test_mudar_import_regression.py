"""Corrections needed to make the uploaded app work against its own UI prompts."""
import pytest
from test_mawid import client


@pytest.mark.parametrize("question", ["كم أقدر أصرف؟", "كم أقدر أصرف الحين؟"])
def test_available_spending_prompt_uses_remaining_balance(client, question):
    response = client.post("/api/chat", json={"message": question})
    assert response.status_code == 200
    assert response.json()["tools"] == ["get_month_summary"]
    assert "180" in response.json()["reply"]
    client.post("/api/expenses", json={"name": "مصروف اختبار", "amount": 20,
                                      "category": "flexible:مطاعم ومقاهي"})
    response = client.post("/api/chat", json={"message": question})
    assert "160" in response.json()["reply"]
    spending = client.post("/api/chat", json={"message": "كم صرفت هالشهر؟"}).json()
    assert spending["tools"] == ["get_spending"]
    assert "440" in spending["reply"]


def test_english_available_spending_uses_remaining_balance(client):
    response = client.post("/api/chat", json={"message": "How much can I spend?", "lang": "en"})
    assert response.status_code == 200
    assert response.json()["tools"] == ["get_month_summary"]
    assert "180" in response.json()["reply"]


def test_legacy_bank_rows_are_tagged_without_resetting_saved_data(client):
    import main
    with main.db.tx() as con:
        con.execute("UPDATE transactions SET bank_id=NULL WHERE source='bank'")
        before = [tuple(r) for r in con.execute(
            "SELECT id,user_id,date,amount,direction,merchant,description,category,source FROM transactions ORDER BY id")]
        con.execute("ALTER TABLE transactions DROP COLUMN source")
    main.db.init()
    main.db.init()
    with main.db.tx() as con:
        after = [tuple(r) for r in con.execute(
            "SELECT id,user_id,date,amount,direction,merchant,description,category,source FROM transactions ORDER BY id")]
        assert before == after
        assert con.execute("SELECT COUNT(*) FROM transactions WHERE bank_id IS NULL").fetchone()[0] == 0
    assert client.get("/api/banks").json()["banks"][0]["transactions"] == len(before)
    client.post("/api/banks", json={"bank_id": "demo2"})
    assert client.delete("/api/banks/demo1").status_code == 200
    with main.db.tx() as con:
        assert not con.execute("SELECT 1 FROM transactions WHERE bank_id='demo1'").fetchone()