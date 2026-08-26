"""간이 인증 저장소 — 닉네임 + 비밀번호 (외부 의존성 없음).

토큰 관리 정책:
- 로그인할 때마다 새 토큰 발급
- 유저별로 최대 MAX_CONCURRENT_TOKENS(3개)까지 동시 보유 가능
- 새 토큰 발급 시 가장 오래된 것부터 초과분을 자동 삭제 (Redis 키도 함께 제거)
- 각 토큰은 30일 후 자동 만료 (TTL)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time

from ..guest import GUEST_TTL_SECONDS, new_guest_nickname

_rc = None
_mem_users: dict[str, dict] = {}
_mem_tokens: dict[str, dict] = {}

TOKEN_TTL = 60 * 60 * 24 * 30          # 토큰 유효기간 30일
USER_KEY_PREFIX = "if:user:"
TOKEN_KEY_PREFIX = "if:token:"
UTOKEN_SET_PREFIX = "if:utokens:"      # 유저별 발급 토큰 목록 (sorted set)
MAX_CONCURRENT_TOKENS = 3              # 동시 보유 가능 토큰 수


class NicknameTakenError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class ValidationError(Exception):
    pass


def _redis():
    global _rc
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    if _rc is None:
        try:
            import redis
            _rc = redis.Redis.from_url(url, decode_responses=True, socket_timeout=5)
            _rc.ping()
            print("[auth] Redis 연결됨 — 계정 영속화 활성화")
        except Exception as e:
            print(f"[auth] Redis 연결 실패, 메모리 폴백: {e}")
            return None
    return _rc


def _norm(nickname: str) -> str:
    return nickname.strip().lower()


def _hash_pw(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 100_000
    ).hex()


def validate(nickname: str, password: str) -> None:
    n = _norm(nickname)
    if n.startswith("guest_"):
        raise ValidationError("사용할 수 없는 닉네임입니다.")
    if len(n) < 2 or len(n) > 20:
        raise ValidationError("닉네임은 2~20자로 입력해주세요.")
    if not all(ch.isalnum() or ch in "_가-힣" for ch in n):
        raise ValidationError("닉네임은 한글/영문/숫자/_만 사용할 수 있습니다.")
    if len(password) < 6:
        raise ValidationError("비밀번호는 6자 이상이어야 합니다.")


def create_user(nickname: str, password: str) -> str:
    """계정 생성 + 즉시 로그인(토큰 발급)."""
    key = _norm(nickname)
    validate(key, password)
    r = _redis()

    exists = (r.exists(USER_KEY_PREFIX + key)) if r else (key in _mem_users)
    if exists:
        raise NicknameTakenError("이미 사용 중인 닉네임입니다.")

    record = {
        "display": nickname.strip(),
        "salt": secrets.token_hex(16),
        "created": time.time(),
        "pw": _hash_pw(password, secrets.token_hex(16)),
    }
    record["pw"] = _hash_pw(password, record["salt"])

    if r:
        r.set(USER_KEY_PREFIX + key, json.dumps(record))
    else:
        _mem_users[key] = record

    return issue_token(record["display"], key)


def login(nickname: str, password: str) -> str:
    key = _norm(nickname)
    r = _redis()
    raw = None
    if r:
        raw = r.get(USER_KEY_PREFIX + key)
    elif key in _mem_users:
        raw = json.dumps(_mem_users[key])

    if not raw:
        raise InvalidCredentialsError("존재하지 않는 닉네임입니다.")
    rec = json.loads(raw)
    if _hash_pw(password, rec["salt"]) != rec["pw"]:
        raise InvalidCredentialsError("비밀번호가 올바르지 않습니다.")
    return issue_token(rec["display"], key)


def issue_token(display_name: str, nickname_key: str | None = None) -> str:
    """새 토큰 발급 + 유저별 목록 추적 + 초과분 자동 삭제."""
    key = nickname_key or _norm(display_name)
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user": display_name, "exp": time.time() + TOKEN_TTL})
    r = _redis()

    if r:
        pipe = r.pipeline()
        pipe.set(TOKEN_KEY_PREFIX + token, payload, ex=TOKEN_TTL)
        tset = UTOKEN_SET_PREFIX + key
        pipe.zadd(tset, {token: time.time()})
        pipe.expire(tset, TOKEN_TTL)
        pipe.execute()

        # 최대 개수 초과 시 가장 오래된 토큰부터 삭제
        members = r.zrange(tset, 0, -(MAX_CONCURRENT_TOKENS + 1))
        for old in members:
            r.delete(TOKEN_KEY_PREFIX + old)
            r.zrem(tset, old)
    else:
        # 메모리 모드
        prev = [t for t, info in _mem_tokens.items() if info.get("nkey") == key]
        if len(prev) >= MAX_CONCURRENT_TOKENS:
            del _mem_tokens[prev[0]]
        _mem_tokens[token] = {"user": display_name, "exp": time.time() + TOKEN_TTL, "nkey": key}

    return token


def create_guest_token() -> str:
    """게스트 토큰 발급 — 계정 생성 없이 24시간 유효."""
    nickname = new_guest_nickname()
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user": nickname, "exp": time.time() + GUEST_TTL_SECONDS})
    r = _redis()
    if r:
        r.set(TOKEN_KEY_PREFIX + token, payload, ex=GUEST_TTL_SECONDS)
    else:
        _mem_tokens[token] = {"user": nickname, "exp": time.time() + GUEST_TTL_SECONDS}
    return token


def user_for_token(token: str) -> str | None:
    """토큰 → 표시용 닉네임. 유효하지 않으면 None."""
    if not token:
        return None
    r = _redis()
    raw = None
    if r:
        raw = r.get(TOKEN_KEY_PREFIX + token)
    elif token in _mem_tokens:
        entry = _mem_tokens[token]
        if entry.get("exp", 0) > time.time():
            return entry.get("user")
        _mem_tokens.pop(token, None)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if isinstance(payload, dict):
        exp = payload.get("exp", 0)
        if exp and exp < time.time():
            return None
        return payload.get("user")
    return None


def revoke_token(token: str) -> None:
    _mem_tokens.pop(token, None)
    r = _redis()
    if r:
        try:
            r.delete(TOKEN_KEY_PREFIX + token)
        except Exception:
            pass
