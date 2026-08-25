"""AI 캐릭터 어시스트.

시스템 프롬프트만 입력받으면 첫 메시지/태그/장르/소개글/예시 대화를
Gemma가 자동 생성해 완성된 캐릭터 카드를 만들어 저장한다.
"""
from __future__ import annotations

import json
import re

from library.creators import builder
from library.inference import gemma_client

ASSIST_PROMPT = """당신은 iF 플랫폼의 캐릭터 설계 전문가다. 아래 시스템 프롬프트를 분석하여 완성도 높은 캐릭터 프로필을 만든다.

[시스템 프롬프트]
{system_prompt}

아래 JSON 형식 **그대로만** 출력하라. 다른 설명 금지. 모든 값은 한국어로.
{{
  "first_message": "캐릭터의 첫 대사 (상황과 성격이 드러나게 1~3문장)",
  "tags": ["성격 키워드", "장르 분위기", "관계성"] ,
  "genre": "장르 하나 (예: 로맨스/RPG/다크 로맨스/무협/판타지/일상/추리)",
  "greeting_mood": "cold|warm|playful|neutral 중 하나",
  "intro": "유저에게 보여줄 캐릭터 소개 3~4문장",
  "example_dialogs": [
    {{"user": "유저의 예시 발화", "character": "캐릭터의 예시 응답"}},
    {{"user": "유저의 예시 발화", "character": "캐릭터의 예시 응답"}}
  ]
}}"""


class AssistError(Exception):
    pass


def _extract_json(text: str) -> dict:
    """모델 출력에서 JSON 객체 추출 (<thought> 제거, 코드펜스 제거)."""
    text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.DOTALL)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise AssistError(f"모델 출력에서 JSON을 찾을 수 없습니다: {text[:200]}")
    return json.loads(text[start:end + 1])


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))
    return f"char_{base or 'custom'}_{int(__import__('time').time()) % 100000}"


def generate_card(system_prompt: str, name: str | None = None, creator: str | None = None) -> dict:
    """시스템 프롬프트 → 완성된 캐릭터 카드 생성 후 저장."""
    raw = gemma_client.generate(ASSIST_PROMPT.format(system_prompt=system_prompt), mood="warm")
    data = _extract_json(raw)

    card = {
        "id": _slugify(name or data.get("genre", "custom")),
        "name": (name or "").strip() or "이름 없는 캐릭터",
        "system_prompt": system_prompt.strip(),
        "first_message": str(data.get("first_message", "")).strip(),
        "tags": [str(t)[:20] for t in data.get("tags", [])][:5] or ["오리지널"],
        "genre": str(data.get("genre", "일상"))[:20],
        "greeting_mood": data.get("greeting_mood", "neutral"),
        "intro": str(data.get("intro", "")).strip(),
        "example_dialogs": [],
        "emoji": "✨",
        "gradient": "linear-gradient(135deg, #f6d365, #fda085)",
    }
    mood_ok = {"cold", "warm", "playful", "neutral"}
    if card["greeting_mood"] not in mood_ok:
        card["greeting_mood"] = "neutral"
    for d in data.get("example_dialogs", [])[:2]:
        if isinstance(d, dict) and d.get("user") and d.get("character"):
            card["example_dialogs"].append({"user": str(d["user"])[:300], "character": str(d["character"])[:500]})
    if not card["first_message"]:
        raise AssistError("첫 메시지 생성에 실패했습니다. 시스템 프롬프트를 더 구체적으로 적어주세요.")
    return builder.save_card(card, creator=creator)
