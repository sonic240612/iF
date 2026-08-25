import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from library.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _auth(monkeypatch):
    """API 테스트용 인증 — 테스트 유저 등록 후 토큰 헤더 자동 첨부."""
    from library.auth import store as auth_store
    monkeypatch.setattr(auth_store, "_rc", None)
    auth_store._mem_users.clear()
    auth_store._mem_tokens.clear()

    r = client.post("/auth/register", json={"nickname": "tester", "password": "pw12345678"})
    token = r.json()["token"] if r.status_code == 200 else None
    if not token:
        r2 = client.post("/auth/login", json={"nickname": "tester", "password": "pw12345678"})
        token = r2.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})


def test_register_and_login_flow():
    c2 = TestClient(app)
    from library.auth import store as auth_store
    auth_store._mem_users.clear()
    auth_store._mem_tokens.clear()

    # 회원가입 → 토큰 발급
    r = c2.post("/auth/register", json={"nickname": "신규유저", "password": "abc12345"})
    assert r.status_code == 200 and r.json()["token"]

    # 중복 가입 거부
    assert c2.post("/auth/register", json={"nickname": "신규유저", "password": "abc12345"}).status_code == 409

    # 로그인
    r = c2.post("/auth/login", json={"nickname": "신규유저", "password": "abc12345"})
    assert r.status_code == 200

    # 잘못된 비밀번호
    assert c2.post("/auth/login", json={"nickname": "신규유저", "password": "wrong!"}).status_code == 401


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
