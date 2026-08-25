# iF (이프)

> 차원의 틈을 넘어, 유저가 서사의 주체가 되는 고몰입 AI 캐릭터 채팅 & 인터랙티브 스토리텔링 플랫폼

iF는 단순한 1회성 AI 챗봇을 넘어, **캐릭터의 살아있는 감정 변화**와 **유저 주도형 분기 내러티브**를 결합한 하이브리드 스토리텔링 플랫폼입니다. Gemma-4 LLM 위에 FSM 기반 감정 엔진과 RAG 장기기억을 얹어, 대화할수록 관계가 깊어지는 캐릭터를 만듭니다.

## ✨ 핵심 기능

### 🎭 FSM 감정 엔진
모든 캐릭터 세션은 `[호감도, 집착도, 혐오, 질투]` 4차원 감정 벡터(0~100)를 실시간으로 유지합니다. 유저 발화가 병렬 감성 분류기를 거쳐 감정 벡터에 즉시 반영되고, 갱신된 상태는 **토큰 생성 이전에** 프롬프트에 주입됩니다.

```
유저: "사랑해, 정말 예뻐"          → 호감도 ↑, 말투가 다정해짐
유저: "다른 사람이랑 데이트했어"     → 질투·집착 급등, 캐릭터가 달라짐
```

감정 벡터에 따라 캐릭터의 어조가 `냉담 → 츤데레 → 다정 → 애정 → 집착 → 적대`로 동적으로 변화하고, UI 테마도 함께 시프트됩니다.

### 📡 SSE 스트리밍 채팅
응답을 기다리지 않고 생성되는 토큰을 그대로 실시간 출력합니다. 체감 대기시간 없이 캐릭터가 "말하는" 몰입감을 제공합니다.

### 🧠 RAG 장기기억
10턴마다 대화가 요약되어 장기기억으로 저장되고, 매 턴 현재 발화와 관련된 과거 기억을 검색해 프롬프트에 자동 주입합니다. *"지난주에 바다 여행 가자고 했잖아"* — 캐릭터가 약속을 기억합니다.

### 🌿 분기형 내러티브 (Choice Cards)
대화 중 핵심 순간에 갈래길 선택지가 등장합니다. 선택지는 문장 그대로 전송되지 않고 **행동 지시**로 처리되어, AI가 그 행동이 일어난 직후의 장면을 이어 그립니다.

### 🎨 Creator Studio
| 직접 만들기 | AI 어시스트 |
|---|---|
| 시스템 프롬프트, 첫 메시지, 태그, 장르, 톤, 카드 색상을 모두 직접 설정 | **시스템 프롬프트 한 줄만 작성하면** 첫 메시지·태그·장르·소개글·예시 대화를 AI가 자동 완성 |

### 🗝️ 멀티 키 라운드로빈
`GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`… 형식으로 키를 무제한 추가할 수 있으며, 요청마다 Round Robin으로 순회합니다. 429 레이트리밋이 걸린 키는 **2분간 자동 쿨다운** 후 로테이션에 복귀하고, 5xx·네트워크 오류·무효 키는 즉시 다음 키로 폴백합니다.

```bash
python -m library.inference.key_cli list / add / remove   # 키 관리 CLI
```

## 🏗️ 아키텍처

```
[Client] React/Vite SPA (PC · 모바일 반응형)
    │  SSE 스트리밍 + REST
[API] FastAPI
    │
    ├─ 감성 분류기 ──┐ (병렬)
    ├─ FSM 감정 엔진 ←┘   Redis-ready 인메모리
    ├─ RAG 장기기억       SQLite (Milvus/Pinecone 교체 지점)
    ├─ 프롬프트 컴파일러   감정+기억+서사지시 주입
    │
[AI Inference] Gemma-4-26b-a4b-it (Gemini API)
    키 라운드로빈 · 429 쿨다운 · 폴백 재시도
```

**파이프라인 불변식:** 유저 발화 → 감성 분류 → FSM 커밋 → 기억 검색 → 프롬프트 주입 → **그 다음** 토큰 생성. 감정 상태는 반드시 생성 이전에 결정적으로 갱신됩니다.

## 🚀 시작하기

### 요구사항
- Python 3.11+
- Node.js 18+

### 설치 및 실행

```bash
# 백엔드 의존성
pip install fastapi uvicorn pydantic tomli

# API 키 설정 (.env)
GOOGLE_API_KEY=your-gemini-api-key
GOOGLE_API_KEY_2=optional-second-key

# 개발 모드 실행
python -m uvicorn library.api:app --port 8000   # 백엔드
cd web && npm install && npm run dev            # 프론트엔드 (http://localhost:5173)
```

> `.env`의 `endpoint = "mock"`으로 바꾸면 API 키 없이도 규칙 기반 응답으로 개발할 수 있습니다.

### 테스트

```bash
python -m pytest tests/ -q
```

## 📁 프로젝트 구조

```
├── configs/
│   ├── base.toml                  # 모델/FSM 전역 설정
│   └── schemas/character_card.json # 캐릭터 카드 JSON Schema
├── characters/methods/            # 캐릭터 카드 (앨리스, 린, 설희, 연우)
├── library/
│   ├── api.py                     # FastAPI 라우팅 (chat/stream, assist, sessions)
│   ├── fsm/
│   │   ├── engine.py              # 감정 벡터 FSM + 무드 도출
│   │   └── classifier.py          # 감성/의도 분류기
│   ├── inference/
│   │   ├── gemma_client.py        # Gemma 추론 (스트리밍, 키 폴백)
│   │   ├── key_manager.py         # 라운드로빈 키 풀 + 쿨다운
│   │   ├── prompt_compiler.py     # 동적 프롬프트 컴파일
│   │   └── narrative.py           # Choice Card 생성
│   ├── memory/store.py            # RAG 장기기억 + 히스토리 영속화
│   └── creators/
│       ├── builder.py             # 캐릭터 카드 검증/저장
│       └── assist.py              # AI 어시스트 자동완성
├── web/src/                       # React SPA (Home / Detail / Chat / Create)
└── tests/                         # pytest
```

## 🔌 API 요약

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/characters` | 캐릭터 목록 |
| `POST` | `/characters` | 캐릭터 카드 직접 등록 |
| `POST` | `/characters/assist` | 시스템 프롬프트만으로 AI 캐릭터 생성 |
| `POST` | `/chat` | 채팅 (일괄 응답) |
| `POST` | `/chat/stream` | 채팅 (SSE 스트리밍) |
| `GET` | `/sessions/{id}/history` | 대화 복원 |
| `DELETE` | `/sessions/{id}` | 대화 초기화 |

## 🛣️ 로드맵

- [ ] Redis 세션 저장소 (멀티 인스턴스 대응)
- [ ] 임베딩 기반 벡터 검색 (Milvus/Pinecone)
- [ ] React Native 모바일 앱

---

*Powered by Gemma · FSM Emotion Engine · RAG Long-term Memory*
