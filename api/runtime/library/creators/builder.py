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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=2)
    return card


def load_character(character_id: str) -> dict | None:
    matches = list(CHARACTERS_DIR.rglob(f"{character_id}.json"))
    if not matches:
        return None
    path = matches[0]
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_characters() -> list[dict]:
    if not CHARACTERS_DIR.exists():
        return []
    out = []
    for p in sorted(CHARACTERS_DIR.rglob("char_*.json")):
        with open(p, encoding="utf-8") as f:
            out.append(json.load(f))
    return out
