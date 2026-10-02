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