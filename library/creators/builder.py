"""캐릭터 카드 파싱/검증 (Creator Studio 기반).

JSON Schema 준수 검증 — core 속성 누락 시 API 게이트웨이 단계에서 거부.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "configs" / "schemas" / "character_card.json"
CHARACTERS_DIR = ROOT / "characters"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)

REQUIRED = SCHEMA["required"]


class ValidationError(Exception):
    pass


# ── Redis 폴백 (서버리스: 읽기 전용 FS라 파일 저장 불가) ──
CARD_KEY_PREFIX = "if:card:"
_rc = None


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


def validate_card(card: dict) -> dict:
    """경량 스키마 검증 (외부 의존성 없음). 실패 시 ValidationError."""
    for key in REQUIRED:
        if key not in card or card[key] in (None, "", []):
            raise ValidationError(f"missing required field: '{key}'")
    if not isinstance(card["tags"], list) or not card["tags"]:
        raise ValidationError("'tags' must be a non-empty array")
    cid = card.get("id", "")
    if not cid.startswith("char_"):
        raise ValidationError("'id' must start with 'char_'")
    if len(card["system_prompt"]) < 10:
        raise ValidationError("'system_prompt' too short (min 10 chars)")
    for d in card.get("example_dialogs", []):
        if not isinstance(d, dict) or "user" not in d or "character" not in d:
            raise ValidationError("example_dialogs items need 'user' and 'character'")
    allowed = set(SCHEMA["properties"])
    unknown = set(card) - allowed
    if unknown:
        raise ValidationError(f"unknown fields: {sorted(unknown)}")
    return card


def save_card(card: dict) -> dict:
    card = validate_card(card)
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARACTERS_DIR / f"{card['id']}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
    except OSError:
        # 읽기 전용 FS(서버리스) → Redis에 저장
        r = _redis()
        if not r:
            raise ValidationError("캐릭터 저장 실패: 쓰기 가능한 스토리지가 없습니다 (REDIS_URL 확인)")
        r.set(CARD_KEY_PREFIX + card["id"], json.dumps(card, ensure_ascii=False))
    return card


def load_character(character_id: str) -> dict | None:
    matches = list(CHARACTERS_DIR.rglob(f"{character_id}.json"))
    if matches:
        with open(matches[0], encoding="utf-8") as f:
            return json.load(f)
    # 파일 시스템에 없으면 Redis에서 찾기 (서버리스에서 생성된 캐릭터)
    r = _redis()
    if r:
        try:
            raw = r.get(CARD_KEY_PREFIX + character_id)
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    return None


def list_characters() -> list[dict]:
    out = []
    seen_ids = set()
    if CHARACTERS_DIR.exists():
        for p in sorted(CHARACTERS_DIR.rglob("char_*.json")):
            try:
                with open(p, encoding="utf-8") as f:
                    out.append(json.load(f))
                    seen_ids.add(out[-1].get("id"))
            except Exception:
                continue
    # Redis에 저장된 (서버리스에서 생성된) 캐릭터 병합
    r = _redis()
    if r:
        try:
            for key in r.scan_iter(CARD_KEY_PREFIX + "*"):
                raw = r.get(key)
                if raw:
                    card = json.loads(raw)
                    if card.get("id") not in seen_ids:
                        out.append(card)
        except Exception:
            pass
    return sorted(out, key=lambda c: c.get("name", ""))
