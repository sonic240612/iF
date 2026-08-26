"""FSM 감정 상태 엔진.

세션별 상태 튜플 [Affection, Obsession, Enmity, Jealousy] (0.0 ~ 100.0)을 관리한다.
불변식: 상태 갱신은 반드시 LLM 토큰 생성 *이전*에 결정적으로(deterministic) 수행된다.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict

from ..guest import GUEST_TTL_SECONDS, is_guest

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
    """세션 스토어.

    REDIS_URL 환경변수가 있으면 Redis에 영속화 (멀티 인스턴스/재시작 대응),
    없으면 인메모리로 동작한다. 두 경로 모두 동일한 인터페이스.
    """
    PREFIX = "if:fsm:"

    def __init__(self) -> None:
        self._sessions: dict[str, EmotionState] = {}
        self._redis = None
        url = os.environ.get("REDIS_URL")
        if url:
            try:
                import redis
                self._redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3)
                self._redis.ping()
                print("[FSM] Redis 연결됨 — 감정 상태 영속화 활성화")
            except Exception as e:
                print(f"[FSM] Redis 연결 실패, 인메모리 폴백: {e}")
                self._redis = None

    def _load(self, session_id: str) -> EmotionState | None:
        if not self._redis:
            return None
        raw = self._redis.get(self.PREFIX + session_id)
        if not raw:
            return None
        d = json.loads(raw)
        return EmotionState(**d)

    def _persist(self, session_id: str, state: EmotionState) -> None:
        if self._redis:
            try:
                key = self.PREFIX + session_id
                self._redis.set(key, json.dumps(state.to_dict()))
                if is_guest(session_id):
                    self._redis.expire(key, GUEST_TTL_SECONDS)
            except Exception as e:
                print(f"[FSM] Redis 저장 실패(메모리만 유지): {e}")

    def get(self, session_id: str) -> EmotionState:
        if session_id not in self._sessions:
            state = self._load(session_id)
            self._sessions[session_id] = state or EmotionState()
        return self._sessions[session_id]

    def exists(self, session_id: str) -> bool:
        if session_id in self._sessions:
            return True
        return self._load(session_id) is not None

    def pop(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
        if self._redis:
            try:
                self._redis.delete(self.PREFIX + session_id)
            except Exception:
                pass

    def commit(self, session_id: str, delta: dict[str, float], decay: float = 0.0) -> EmotionState:
        state = self.get(session_id)
        state.apply_delta(delta, decay=decay)
        self._persist(session_id, state)
        return state


engine = FSMEngine()
