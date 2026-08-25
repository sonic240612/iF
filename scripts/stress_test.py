"""시스템 프롬프트 길이 스트레스 테스트.

지정한 글자 수(기본 7,000자)의 세계관 설정(로어)을 생성해 캐릭터로 등록하고,
프로덕션 API에 실제 채팅 요청을 보내 응답 시간/잘림 여부를 측정한다.

사용법:
    python -X utf8 scripts/stress_test.py --base-url https://if-chat-plum.vercel.app --chars 7000
"""
from __future__ import annotations

import argparse
import json
import random
import time
import urllib.request

TOPICS = [
    ("왕국의 역사", "{n}년 전 대륙 통일 전쟁에서 승리한 왕국은 이후 {n}번의 반란을 겪으며 현재의 의회제로 발전했다."),
    ("마법 체계", "마력은 대기 중의 {n}가지 속성 입자로 구성되며, 각 속성은 상호 증폭·상쇄 관계에 있다."),
    ("길드 규칙", "모험가 길드는 등급 {n}부터 {n}까지 나뉘며, 승급 시험은 계절마다 열린다."),
    ("주요 인물", "대장장이 카일은 {n}년째 같은 망치를 사용하며, 그 검은 마왕 토벌 당시의 유물이다."),
    ("지리", "북방의 얼어붙은 호수는 겨울마다 {n}미터 두께로 얼어 국경 무역로로 쓰인다."),
    ("경제", "왕국 화폐 단위는 금화/은화/동화이며, 빵 한 덩이는 동화 {n}닢 정도다."),
    ("종교", "달의 여신을 섬기는 교단은 {n}개 분파로 나뉘고 서로 신학 논쟁을 벌인다."),
    ("음식", "수도의 명물 스튜에는 재료가 {n}가지 들어가며, 레시피는 조합장 치외법권이다."),
]


def generate_lore(target_chars: int) -> str:
    rng = random.Random(42)
    parts: list[str] = []
    size = 0
    i = 0
    while size < target_chars:
        topic, tpl = TOPICS[i % len(TOPICS)]
        entry = f"[설정 #{i + 1}] ({topic}) " + tpl.format(n=rng.randint(2, 999)) + "\n"
        # 다양성 확보: 부가 문단 추가
        entry += f"세부 사항: 기록자 {rng.choice(['바르톤', '셀린', '도한', '유리'])}의 필기 — "
        entry += f"신뢰도 {rng.randint(1, 5)}점. 관련 문서 제{i + 7}권 {rng.randint(1, 400)}페이지 참조.\n\n"
        parts.append(entry)
        size += len(entry)
        i += 1
    text = "".join(parts)
    # 초과분 절삭
    return text[:target_chars]


def post_json(url: str, payload: dict, timeout: int = 120):
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    return urllib.request.urlopen(req, timeout=timeout)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--chars", type=int, default=7000)
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    # 1) 로어 생성
    lore = generate_lore(args.chars)
    print(f"=== [1] 시스템 프롬프트 생성: {len(lore):,}자 ===")

    card = {
        "id": f"char_stress_{random.randint(10000, 99999)}",
        "name": "로어 테스트",
        "emoji": "📚",
        "gradient": "linear-gradient(135deg, #f6d365, #fda085)",
        "system_prompt": (
            "당신은 방대한 세계관 지식을 가진 사서 로라다. 아래 설정을 모두 알고 있으며 "
            "유저의 질문에 근거 자료를 인용하듯 답한다.\n\n" + lore
        ),
        "first_message": "방대한 서고에 온 것을 환영해. 무엇이 궁금하지?",
        "tags": ["스트레스테스트"],
        "genre": "판타지",
        "greeting_mood": "warm",
    }

    # 2) 캐릭터 등록
    t0 = time.perf_counter()
    with post_json(f"{base}/api/characters", card) as resp:
        saved = json.load(resp)
    print(f"=== [2] 캐릭터 등록 성공: {saved['id']} ({time.perf_counter() - t0:.2f}s) ===")

    # 3) SSE 스트리밍 채팅
    question = "이 왕국의 마법 체계와 길드 승급 규칙을 요약해서 알려줄래?"
    print(f"=== [3] 채팅 스트리밍 시작 ===\n질문: {question}")

    payload = {
        "character_id": saved["id"],
        "session_id": f"stress_{random.randint(1000, 9999)}",
        "message": question,
    }
    t1 = time.perf_counter()
    first_event_at = None
    deltas = 0
    chars_out = 0
    done_event = None
    error_event = None

    with post_json(f"{base}/api/chat/stream", payload, timeout=300) as resp:
        buffer = ""
        for raw in resp:
            line = raw.decode("utf-8", errors="ignore").strip()
            if not line.startswith("data:"):
                continue
            evt = json.loads(line[5:])
            if first_event_at is None:
                first_event_at = time.perf_counter() - t1
            if evt["type"] == "delta":
                deltas += 1
                chars_out += len(evt["text"])
            elif evt["type"] == "done":
                done_event = evt
            elif evt["type"] == "error":
                error_event = evt
                break

    total = time.perf_counter() - t1
    print(f"첫 이벤트 도달: {first_event_at:.2f}s")
    print(f"delta 청크 수: {deltas} | 응답 글자 수: {chars_out:,}")
    print(f"총 소요: {total:.2f}s")
    if done_event:
        print(f"truncated(잘림 감지): {done_event.get('truncated')}")
        print(f"memory_saved: {done_event.get('memory_saved')}, 총 기억: {done_event.get('total_memories')}")
    if error_event:
        print(f"⚠️ 에러 이벤트: {error_event.get('detail')}")

    verdict = "✅ 통과" if done_event and not error_event else "❌ 실패"
    print(f"\n결과: {verdict}")


if __name__ == "__main__":
    main()
