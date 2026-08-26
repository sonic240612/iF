"""세션별 휘발성 메타 데이터 (초기 설정 / 유저 패치) 저장소.

- 초기 설정: 세션 첫 대화 시점에 캐릭터 카드에서 스냅샷으로 고정
- 유저 패치: 유저가 채팅 중 수시로 수정 가능, 상시 유지

저장 위치: REDIS_URL 있으면 Redis, 없으면 프로세스 메모리.
"""
from __future__ import annotations

import json
import os
import time

from ..guest import GUEST_TTL_SECONDS, is_guest

_rc = None
_mem: dict[str, dict] = {}

INITIAL_SETUP_MAX = 1000
USER_PATCH_MAX = 1000


def _redis():
    global _rc
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    if _rc is None:
        try:
            import redis
            _rc = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3)
            _rc.ping()
        except Exception:
            return None
    return _rc


def _key(session_id: str) -> str:
    return f"if:meta:{session_id}"


def _load(session_id: str) -> dict | None:
    r = _redis()
    if r:
        raw = r.get(_key(session_id))
        return json.loads(raw) if raw else None
    return _mem.get(session_id)


def _save(session_id: str, data: dict) -> None:
    data["updated_at"] = time.time()
    r = _redis()
    if r:
        key = _key(session_id)
        r.set(key, json.dumps(data, ensure_ascii=False))
        if is_guest(session_id):
            r.expire(key, GUEST_TTL_SECONDS)
    else:
        _mem[session_id] = data


def exists(session_id: str) -> bool:
    return _load(session_id) is not None


def init_if_absent(session_id: str, initial_setup: str) -> dict:
    """세션 첫 대화 시 초기 설정을 스냅샷으로 고정. 이미 있으면 기존 값 반환."""
    existing = _load(session_id)
    if existing is not None:
        return existing
    data = {"initial_setup": (initial_setup or "")[:INITIAL_SETUP_MAX], "user_patch": ""}
    _save(session_id, data)
    return data


def get_meta(session_id: str) -> dict:
    return _load(session_id) or {}


def set_user_patch(session_id: str, patch: str) -> None:
    data = get_meta(session_id)
    data["user_patch"] = (patch or "").strip()[:USER_PATCH_MAX]
    _save(session_id, data)


def delete(session_id: str) -> None:
    _mem.pop(session_id, None)
    r = _redis()
    if r:
        try:
            r.delete(_key(session_id))
        except Exception:
            pass
