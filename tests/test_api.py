import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from library.api import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_character_list():
    chars = client.get("/characters").json()
    assert any(c["id"] == "char_alice_01" for c in chars)


def test_chat_updates_fsm_state():
    sess = "sess_test_1"
    r1 = client.post(
        "/chat",
        json={"character_id": "char_alice_01", "session_id": sess, "message": "사랑해, 정말 예뻐"},
    ).json()
    assert r1["intent"] == "affectionate"
    assert r1["state"]["affection"] > 30.0  # 초기값보다 상승했는가

    # 질투 트리거 → jealousy 급등 확인
    r2 = client.post(
        "/chat",
        json={"character_id": "char_alice_01", "session_id": sess, "message": "어제 다른 사람이랑 데이트했어"},
    ).json()
    assert r2["state"]["jealousy"] >= 10.0
    assert len(r2["choice_cards"]) in (2, 3)
    assert r2["reply"]


def test_chat_unknown_character_404():
    r = client.post("/chat", json={"character_id": "char_none", "session_id": "s", "message": "hi"})
    assert r.status_code == 404


def test_create_character_validation():
    bad = {"id": "bad_id", "name": "x"}  # 필수 필드 누락
    assert client.post("/characters", json=bad).status_code == 422
