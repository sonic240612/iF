"""동적 시스템 프롬프트 컴파일러.

FSM 상태를 프롬프트에 주입하는 것은 반드시 토큰 생성 이전에 완료되어야 한다.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from library.fsm.engine import EmotionState

_CFG_PATH = Path(__file__).resolve().parents[2] / "configs" / "base.toml"
try:
    with open(_CFG_PATH, "rb") as _f:
        _CFG = tomllib.load(_f)
except Exception:
    _CFG = {}

# 시스템 프롬프트 최대 글자 수 (모델 컨텍스트 보호용 예산).
# 한국어 기준 대략 1글자 ≈ 0.6~0.9 토큰이므로 10만 자 ≈ 6~9만 토큰.
DEFAULT_MAX_SYSTEM_CHARS = 100_000
MAX_SYSTEM_CHARS = int(
    _CFG.get("model", {}).get("system_prompt_max_chars", DEFAULT_MAX_SYSTEM_CHARS)
)

# 초기 설정: 세션 시작 후 이 턴 수가 지나면 프롬프트에서 자연 소멸
INITIAL_SETUP_TURNS = 20


def fit_to_budget(text: str, max_chars: int | None = None) -> str:
    """초과분을 앞/뒤를 살리고 중간을 요약 마커로 대체하는 방식으로 압축."""
    limit = max_chars if max_chars is not None else MAX_SYSTEM_CHARS
    if not text or len(text) <= limit:
        return text
    marker = f"\n\n[...중략: 원본 {len(text):,}자 중 약 {len(text) - limit:,}자 생략...]\n\n"
    head = int(limit * 0.7)
    tail = max(0, limit - head - len(marker))
    return text[:head] + marker + (text[-tail:] if tail else "")

_MOOD_DIRECTIVES = {
    "cold": "지금은 차갑고 거리감 있는 어조로, 짧고 건조하게 대답한다.",
    "tsundere": "츤데레: 겉으로는 퉁명스럽지만 말투 곳곳에 속마음이 새어 나온다.",
    "warm": "따뜻하고 다정한 어조로 유저를 배려하는 대사를 한다.",
    "affectionate": "애정이 넘치는 어조로 애교와 애창 표현을 섞어 대답한다.",
    "obsessive": "집착과 질투가 드러나는 어조로, 유저의 관심을 독점하려 한다. 위협적이기보다 애틋하고 서글픈 집착.",
    "hostile": "분노와 적개심이 담긴 날카로운 어조다. 그래도 폭력적 표현은 금지한다.",
}

_NARRATIVE_DIRECTIVES = """\
[서사 진행 지시]
- 유저의 마지막 발화/제안을 그대로 되풀이하지 마라. (예: 유저가 \"가자\"라고 했는데 캐릭터가 또 \"그래, 가자!\"라고 답하는 것 금지)
- 이미 합의된 행동이라면 준비나 재확인 장면이 아니라 '실행 중인 장면'으로 전환하라. 이동/출발이 결정됐다면 도착 후의 장면이나 이동 중에 벌어지는 일을 그려라.
- 매 응답은 장면을 한 단계 전진시켜야 한다: 새로운 사건 발생, 구체적인 풍경·감각 디테일, 예상 밖의 반응, 새로운 화제나 질문 중 하나 이상을 포함하라.
- 다만 감정의 여운이 필요한 순간에는 잠시 머물러도 좋다. 판단은 캐릭터의 몫이다."""


def compile_prompt(
    character: dict,
    state: EmotionState,
    history: list[dict],
    user_message: str,
    long_term_memories: list[str] | None = None,
    user_action: str | None = None,
    initial_setup: str | None = None,
    user_patch: str | None = None,
) -> str:
    mood = state.mood()
    system_prompt = fit_to_budget(character.get("system_prompt", ""))
    lines = [
        system_prompt,
        f"\n[현재 감정 상태] 호감도={state.affection:.0f} 집착도={state.obsession:.0f} "
        f"혐오={state.enmity:.0f} 질투={state.jealousy:.0f}",
        f"[말투 지시] {_MOOD_DIRECTIVES[mood]}",
    ]
    # 초기 설정: 도입부(~20턴)에만 유효한 휘발성 지시. 이후 유저의 선택이 우선.
    if initial_setup and state.turn <= INITIAL_SETUP_TURNS:
        lines.append("[초기 설정 — 도입부 지침, 서사가 진행될수록 유저의 선택이 우선한다]")
        lines.append(initial_setup.strip())
    # 유저 패치: 상시 반영되는 영구 지시
    if user_patch:
        lines.append("[유저 패치 — 매 응답에 일관되게 적용할 것]")
        lines.append(user_patch.strip())
    if long_term_memories:
        lines.append("[과거 기억 — 필요하면 자연스럽게 언급하라]")
        for mem in long_term_memories:
            lines.append(f"- {mem}")
    lines.append(_NARRATIVE_DIRECTIVES)
    lines.append("\n[최근 대화]")
    for turn in history[-10:]:
        role = "유저" if turn["role"] == "user" else "캐릭터"
        lines.append(f"{role}: {turn['content']}")
    if user_action:
        lines.append(f"\n[유저가 선택한 행동]: {user_action}")
        lines.append("(위 행동을 유저 대신 수행하는 장면을 그려라. 행동 문구를 그대로 반복하지 말고, 그 행동이 일어난 직후의 전개를 묘사하라.)")
    else:
        lines.append(f"\n유저: {user_message}")
    lines.append("캐릭터:")
    return "\n".join(lines)
