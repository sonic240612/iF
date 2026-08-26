"""게스트 모드 정책 — 로그인 없이 채팅 가능, 데이터는 마지막 활동 24시간 후 자동 소멸.

- 게스트 닉네임: `guest_{8hex}` (계정 생성 없음)
- 게스트 세션의 모든 Redis 키에 24시간 TTL을 부여해 만료 시 자동 정리된다.
"""
from __future__ import annotations

import secrets

GUEST_PREFIX = "guest_"
GUEST_TTL_SECONDS = 60 * 60 * 24   # 24시간 (마지막 활동 기준 슬라이딩)


def new_guest_nickname() -> str:
    return f"{GUEST_PREFIX}{secrets.token_hex(4)}"


def is_guest(nickname_or_session_id: str | None) -> bool:
    """닉네임 또는 `{닉네임}:{캐릭터ID}` 세션 키에서 게스트 여부 판별."""
    user = (nickname_or_session_id or "").split(":", 1)[0]
    return user.startswith(GUEST_PREFIX)


def ttl_for(session_id: str, default_seconds: int) -> int:
    """게스트 세션은 24시간 고정 TTL, 일반 유저는 전달된 기본값 사용."""
    return GUEST_TTL_SECONDS if is_guest(session_id) else default_seconds
