"""FSM 감정 상태 엔진.

세션별 상태 튜플 [Affection, Obsession, Enmity, Jealousy] (0.0 ~ 100.0)을 관리한다.
불변식: 상태 갱신은 반드시 LLM 토큰 생성 *이전*에 결정적으로(deterministic) 수행된다.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict

BOUNDS = (0.0, 100.0)
DIMENSIONS = ("affection", "obsession", "enmity", "jealousy")


@dataclass
class EmotionState:
    affection: float = 30.0   # 호감도
    obsession: float = 5.0    # 집착도
    enmity: float = 0.0       # 혐오 지수
    jealousy: float = 0.0     # 질투 게이지
    turn: int = 0
    updated_at: float = field(default_factory=time.time)

    def clamp(self) -> None:
        for d in DIMENSIONS:
            v = max(BOUNDS[0], min(BOUNDS[1], getattr(self, d)))
            setattr(self, d, round(v, 2))

    def apply_delta(self, delta: dict[str, float], decay: float = 0.0) -> "EmotionState":
        """결정적 상태 갱신. 생성 파이프라인에서 유일하게 허용되는 mutation 지점."""
        self.turn += 1
        if decay:
            for d in DIMENSIONS:
                setattr(self, d, getattr(self, d) - decay)
        for d, dv in delta.items():
            if d in DIMENSIONS:
                setattr(self, d, getattr(self, d) + dv)
        self.clamp()
        self.updated_at = time.time()
        return self

    def mood(self) -> str:
        """현재 감정 벡터에서 말투 톤 도출."""
        if self.enmity >= 60:
            return "hostile"
        if self.jealousy >= 50 or self.obsession >= 60:
            return "obsessive"
        if self.affection >= 70:
            return "affectionate"
        if self.affection >= 45:
            return "warm"
        if self.affection >= 25:
            return "tsundere"
        return "cold"

    def to_dict(self) -> dict:
        return asdict(self)


class FSMEngine:
    """인메모리 세션 스토어 (운영 시 Redis로 교체되는 지점)."""

    def __init__(self) -> None:
        self._sessions: dict[str, EmotionState] = {}

    def get(self, session_id: str) -> EmotionState:
        return self._sessions.setdefault(session_id, EmotionState())

    def commit(self, session_id: str, delta: dict[str, float], decay: float = 0.0) -> EmotionState:
        state = self.get(session_id)
        return state.apply_delta(delta, decay=decay)


engine = FSMEngine()
