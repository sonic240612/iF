"""분기형 내러티브 엔진.

유저 발화 후 핵심 분기점에서 Choice Card(2~3개)를 생성한다.
MVP는 FSM 상태/의도 기반 규칙 생성, 이후 LLM 기반 동적 선택지로 확장.
"""
from __future__ import annotations

import random

from library.fsm.classifier import IntentResult

_BRANCH_TEMPLATES = {
    "affectionate": [
        {"text": "솔직하게 마음을 고백한다", "mood_hint": "affectionate", "delta": {"affection": 8}},
        {"text": "놀려대며 밀당을 즐긴다", "mood_hint": "tsundere", "delta": {"affection": 3, "jealousy": -2}},
        {"text": "조용히 손을 잡아준다", "mood_hint": "warm", "delta": {"affection": 5}},
    ],
    "jealousy_trigger": [
        {"text": "즉시 해명하고 안심시킨다", "mood_hint": "warm", "delta": {"jealousy": -10}},
        {"text": "일부러 더 자극한다", "mood_hint": "obsessive", "delta": {"jealousy": 8, "obsession": 5}},
        {"text": "화제를 돌린다", "mood_hint": "cold", "delta": {"jealousy": 3}},
    ],
    "hostile": [
        {"text": "진심으로 사과한다", "mood_hint": "warm", "delta": {"enmity": -12, "affection": 2}},
        {"text": "맞불을 놓는다", "mood_hint": "hostile", "delta": {"enmity": 6}},
        {"text": "자리를 뜬다", "mood_hint": "cold", "delta": {"obsession": 4}},
    ],
    "neutral": [
        {"text": "더 가까이 다가간다", "mood_hint": "warm", "delta": {"affection": 4}},
        {"text": "장난스럽게 군다", "mood_hint": "playful", "delta": {"affection": 2, "obsession": 1}},
        {"text": "묵묵히 들어준다", "mood_hint": "neutral", "delta": {}},
    ],
    "flirty": [
        {"text": "밀당으로 받아친다", "mood_hint": "tsundere", "delta": {"affection": 5}},
        {"text": "분위기를 탄다", "mood_hint": "affectionate", "delta": {"affection": 7}},
    ],
}


def build_choice_cards(intent: IntentResult, mood: str, k: int = 3) -> list[dict]:
    pool = list(_BRANCH_TEMPLATES.get(intent.intent, _BRANCH_TEMPLATES["neutral"]))
    random.shuffle(pool)
    return pool[:k]
