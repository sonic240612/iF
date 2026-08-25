import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

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


# ── AI 어시스트 JSON 추출 ──

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
