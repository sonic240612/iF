"""경량 감성/의도 분류기.

메인 LLM 요청과 병렬로 실행되어 FSM 델타를 산출한다.
MVP는 규칙 기반(키워드+점수)이며, 이후 소형 분류 모델로 교체 가능한 인터페이스.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class IntentResult:
    delta: dict[str, float]
    intent: str


_POSITIVE = ["사랑", "좋아", "고마워", "예뻐", "귀여워", "보고싶", "함께", "믿어", "웃겨"]
_NEGATIVE = ["싫어", "꺼져", "미워", "한심", "시끄러", "신경꺼", "바보"]
_FLIRTY = ["설레", "심쿵", "밀당", "장난", "윙크", "스킨십", "손잡"]
_THIRD_PARTY = ["다른 남자", "다른 여자", "다른 사람", "전 애인", "친구랑", "헤어질"]
_APOLOGY = ["미안", "사과", "잘못했"]


def classify(message: str) -> IntentResult:
    text = message.lower()
    delta: dict[str, float] = {}
    intent = "neutral"

    def hits(words: list[str]) -> int:
        return sum(1 for w in words if w in text)

    if h := hits(_POSITIVE):
        delta["affection"] = 4.0 * h
        delta["enmity"] = -2.0 * h
        intent = "affectionate"

    if h := hits(_NEGATIVE):
        delta["affection"] = -6.0 * h
        delta["enmity"] = 8.0 * h
        intent = "hostile"

    if h := hits(_FLIRTY):
        delta["affection"] = 2.0 * h
        delta["jealousy"] = -1.0 * h
        intent = "flirty"

    if hits(_THIRD_PARTY):
        delta["jealousy"] = 12.0
        delta["obsession"] = 6.0
        intent = "jealousy_trigger"

    if h := hits(_APOLOGY):
        delta["enmity"] = -5.0 * h
        delta["affection"] = 1.0 * h
        intent = "apology"

    if not delta:
        delta["obsession"] = 0.5  # 중립 발화에도 미세한 집착 누적

    return IntentResult(delta=delta, intent=intent)
