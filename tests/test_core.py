import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from fastapi.testclient import TestClient

from library.api import app
from library.fsm.engine import EmotionState
from library.fsm.classifier import classify
from library.creators.assist import _extract_json, AssistError
from library.inference.gemma_client import strip_thought


# ── FSM 엔진 ──

def test_fsm_clamp_bounds():
    s = EmotionState(affection=95, obsession=3)
    s.apply_delta({"affection": 50})   # 145 → 100으로 clamp
    assert s.affection == 100.0
    s.apply_delta({"affection": -200})
    assert s.affection == 0.0          # -105 → 0으로 clamp
    s.apply_delta({"unknown_dim": 5})  # 알 수 없는 차원은 무시
    assert s.turn == 3


def test_fsm_mood_transitions():
    cold = EmotionState()
    assert cold.mood() in ("cold", "tsundere")
    loving = EmotionState(affection=80)
    assert loving.mood() == "affectionate"
    jealous = EmotionState(jealousy=60)
    assert jealous.mood() == "obsessive"
    angry = EmotionState(enmity=90)
    assert angry.mood() == "hostile"


def test_fsm_decay():
    s = EmotionState(affection=50)
    s.apply_delta({}, decay=2.0)
    assert s.affection == 48.0


# ── 감성 분류기 ──

def test_classifier_positive():
    r = classify("사랑해 정말 예뻐")
    assert r.intent == "affectionate"
    assert r.delta["affection"] > 0


def test_classifier_jealousy_trigger():
    r = classify("어제 다른 사람이랑 데이트했어")
    assert r.intent == "jealousy_trigger"
    assert r.delta["jealousy"] >= 10


def test_classifier_neutral_accumulates_obsession():
    r = classify("오늘 날씨 어때")
    assert "obsession" in r.delta


# ── 초기 설정 / 유저 패치 ──

def test_compile_initial_setup_fades_after_20_turns():
    from library.inference.prompt_compiler import compile_prompt
    from library.fsm.engine import EmotionState

    char = {"system_prompt": "기본 설정"}
    early = EmotionState(turn=5)
    p1 = compile_prompt(char, early, [], "안녕", initial_setup="도입부에서 비가 온다")
    assert "도입부에서 비가 온다" in p1

    late = EmotionState(turn=25)
    p2 = compile_prompt(char, late, [], "안녕", initial_setup="도입부에서 비가 온다")
    assert "초기 설정" not in p2  # 20턴 이후 소멸


def test_compile_user_patch_always_injected():
    from library.inference.prompt_compiler import compile_prompt
    from library.fsm.engine import EmotionState

    char = {"system_prompt": "기본 설정"}
    s = EmotionState(turn=100)
    p = compile_prompt(char, s, [], "안녕", user_patch="묘사는 짧고 문학적으로")
    assert "유저 패치" in p and "묘사는 짧고 문학적으로" in p


def test_sanitize_reply_strips_meta_blocks():
    from library.api import sanitize_reply

    dirty = "(서류를 내려놓으며)\n[현재 감정 상태] 호감도=80 집착도=5\n자, 앉으세요.\n\n\n[말투 지시] 따뜻하게"
    clean = sanitize_reply(dirty)
    assert "호감도" not in clean and "말투 지시" not in clean
    assert "앉으세요" in clean and "자, 앉으세요." in clean

def test_session_patch_endpoints(api):
    client = api
    sid = "patch_test_sess"
    # 초기값은 빈 문자열
    assert client.get(f"/api/sessions/{sid}/user-patch").json() == {"patch": ""}
    # 저장
    r = client.put(f"/api/sessions/{sid}/user-patch", json={"patch": "전투는 박진감 있게"})
    assert r.json()["status"] == "ok"
    assert client.get(f"/api/sessions/{sid}/user-patch").json()["patch"] == "전투는 박진감 있게"
    # 리셋 시 삭제됨
    client.delete(f"/sessions/{sid}")
    assert client.get(f"/api/sessions/{sid}/user-patch").json()["patch"] == ""


def test_character_card_with_initial_setup(api):
    client = api
    card = {
        "id": f"char_meta_{random.randint(1000,9999)}",
        "name": "메타테스트",
        "system_prompt": "당신은 테스트용 캐릭터이다.",
        "first_message": "반가워",
        "tags": ["테스트"],
        "initial_setup": "첫 만남은 비 오는 정류장에서",
    }
    r = client.post("/characters", json=card)
    assert r.status_code == 200
    detail = client.get(f"/characters/{card['id']}").json()
    assert detail["initial_setup"] == "첫 만남은 비 오는 정류장에서"

def test_character_edit_ownership(api):
    """제작자만 수정 가능 + 타인/공식 카드는 403"""
    r = api.post("/characters", json={
        "id": f"char_own_{random.randint(1000,9999)}",
        "name": "내캐릭", "system_prompt": "당신은 테스트 캐릭터입니다.",
        "first_message": "hi", "tags": ["테스트"], "intro": "소개",
    })
    assert r.status_code == 200
    cid = r.json()["id"]
    assert r.json()["creator"] == "테스터"
    assert "커스텀" in r.json()["tags"]

    # 제작자 본인 수정 → 성공
    r = api.put(f"/characters/{cid}", json={"name": "수정된이름"})
    assert r.status_code == 200 and r.json()["name"] == "수정된이름"

    # 다른 유저가 수정 시도 → 403
    other = TestClient(app)
    other.post("/auth/register", json={"nickname": "다른사람", "password": "pw12345678"})
    tok = other.post("/auth/login", json={"nickname": "다른사람", "password": "pw12345678"}).json()["token"]
    r = other.put(f"/characters/{cid}", json={"name": "해킹시도"},
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


def test_official_card_not_editable(api):
    """공식 카드(제작자 없음)는 누구도 수정 불가 → 403"""
    r = api.put("/characters/char_alice_01", json={"name": "바꾸기 시도"})
    assert r.status_code == 403


def test_extract_json_plain():
    data = _extract_json('{"first_message": "안녕", "tags": ["a"]}')
    assert data["first_message"] == "안녕"


def test_extract_json_with_thought_and_fence():
    raw = '<thought>생각 중...</thought>```json\n{"first_message": "하이"}\n```'
    assert _extract_json(raw)["first_message"] == "하이"


def test_extract_json_failure():
    with pytest.raises(AssistError):
        _extract_json("JSON이 아닌 텍스트")


# ── thought 제거 ──

def test_strip_thought():
    assert strip_thought("<thought>추론</thought>본문") == "본문"
    assert strip_thought("그냥 텍스트") == "그냥 텍스트"


# ── RAG 장기기억 (임시 DB 격리) ──

def test_memory_save_search_delete(tmp_memory_db):
    store = tmp_memory_db
    store.save_memory("sess_a", 1, "유저는 린에게 다음 주에 바다 여행을 가자고 약속했다")
    store.save_memory("sess_a", 2, "캐릭터가 초콜릿을 선물했다")
    store.save_memory("sess_b", 1, "다른 세션의 기억")

    found = store.search_memories("sess_a", "바다 여행 언제 가?")
    assert any("바다" in f for f in found)
    # 세션 격리 확인
    assert all("다른 세션" not in f for f in found)

    store.delete_history("sess_a")
    assert store.count_memories("sess_a") == 0
    assert store.count_memories("sess_b") == 1


def test_memory_semantic_fallback(tmp_memory_db):
    """임베딩 None(conftest)일 때 토큰 오버랩 폴백 동작."""
    store = tmp_memory_db
    store.save_memory("sess_x", 1, "유저와 산책을 약속했다")
    found = store.search_memories("sess_x", "산책")
    assert len(found) == 1


def test_history_persistence(tmp_memory_db):
    store = tmp_memory_db
    store.save_history("s1", [{"role": "user", "content": "안녕"}])
    assert store.load_history("s1")[0]["content"] == "안녕"
    store.save_history("s1", [{"role": "user", "content": "갱신"}])  # upsert
    assert len(store.load_history("s1")) == 1
