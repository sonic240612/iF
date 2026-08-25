"""간이 인증 저장소 — 닉네임 + 비밀번호 (외부 의존성 없음).

- 비밀번호: PBKDF2-HMAC-SHA256 (솔트 개별 부여)
- 사용자/토큰: REDIS_URL 있으면 Redis 영속화, 없으면 프로세스 메모리
- 닉네임은 소문자 기준으로 중복 검사 (대소문자 무시)
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time

_rc = None
_mem_users: dict[str, dict] = {}
_mem_tokens: dict[str, dict] = {}

TOKEN_TTL = 60 * 60 * 24 * 30  # 30일
USER_KEY_PREFIX = "if:user:"
TOKEN_KEY_PREFIX = "if:token:"


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
    if len(n) < 2 or len(n) > 20:
        raise ValidationError("닉네임은 2~20자로 입력해주세요.")
    if not all(ch.isalnum() or ch in "_가-힣" for ch in n):
        raise ValidationError("닉네임은 한글/영문/숫자/_만 사용할 수 있습니다.")
    if len(password) < 6:
        raise ValidationError("비밀번호는 6자 이상이어야 합니다.")


def create_user(nickname: str, password: str) -> str:
    """계정 생성 후 즉시 로그인용 토큰 반환."""
    key = _norm(nickname)
    validate(key, password)
    r = _redis()

    if r and r.exists(USER_KEY_PREFIX + key):
        raise NicknameTakenError("이미 사용 중인 닉네임입니다.")
    if not r and key in _mem_users:
        raise NicknameTakenError("이미 사용 중인 닉네임입니다.")

    record = {
        "display": nickname.strip(),
        "salt": secrets.token_hex(16),
        "created": time.time(),
    }
    record["pw"] = _hash_pw(password, record["salt"])

    if r:
        r.set(USER_KEY_PREFIX + key, json.dumps(record))
    else:
        _mem_users[key] = record

    return _issue_token(record["display"])


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
    return _issue_token(rec["display"])


def _issue_token(display_name: str) -> str:
    token = secrets.token_urlsafe(32)
    payload = json.dumps({"user": display_name, "exp": time.time() + TOKEN_TTL})
    r = _redis()
    if r:
        r.set(TOKEN_KEY_PREFIX + token, payload, ex=TOKEN_TTL)
    else:
        _mem_tokens[token] = {"payload": payload, "exp": time.time() + TOKEN_TTL}
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
        if entry["exp"] > time.time():
            raw = entry["payload"]
        else:
            _mem_tokens.pop(token, None)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if isinstance(payload, dict) and payload.get("user"):
        return payload["user"]
    return None


def revoke_token(token: str) -> None:
    _mem_tokens.pop(token, None)
    r = _redis()
    if r:
        try:
            r.delete(TOKEN_KEY_PREFIX + token)
        except Exception:
            pass
