---
title: iF
emoji: 🌌
colorFrom: indigo
colorTo: pink
sdk: gradio
app_file: app.py
pinned: false
---

# iF (이프)

> 차원의 틈을 넘어, 유저가 서사의 주체가 되는 고몰입 AI 캐릭터 채팅 & 인터랙티브 스토리텔링 플랫폼

**🔗 라이브 데모: https://if-chat-plum.vercel.app**

iF는 단순한 1회성 AI 챗봇을 넘어, **캐릭터의 살아있는 감정 변화**와 **유저 주도형 분기 내러티브**를 결합한 하이브리드 스토리텔링 플랫폼입니다. Gemma 4 / Gemini 3.5 Flash Lite LLM 위에 FSM 기반 감정 엔진과 RAG 장기기억을 얹어, 대화할수록 관계가 깊어지는 캐릭터를 만듭니다.

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

**대사/묘사 자동 구분**: 대사는 `"큰따옴표"`, 생각·행동·장면 묘사는 `*별표*` 형식으로 표준화되어 있어, 화면에서는 묘사 부분이 흐린 이탤릭으로 자동 표시됩니다. 스트리밍 중에도 동일하게 적용됩니다. 묘사와 대사 사이 줄바꿈 구분은 모델에 관계없이 프롬프트 출력 규칙에서 강제합니다.

### 🔀 듀얼 모델 지원
채팅 화면의 모델 선택기로 두 LLM을 실시간 전환할 수 있습니다(선택은 브라우저에 자동 저장되어 재방문 시 유지됨).

| 모델 | 특징 |
|---|---|
| **Gemma 4** (`gemma-4-26b-a4b-it`) | 풍부한 서사·묘사, 몰입감 우선 |
| **Gemini 3.5 Flash Lite** (`gemini-3.5-flash-lite`) | 빠른 응답(첫 토큰 ~2초), 가벼운 대화에 적합 |

### 🧠 RAG 장기기억
10턴마다 대화가 요약되어 장기기억으로 저장되고, 매 턴 현재 발화와 관련된 과거 기억을 검색해 프롬프트에 자동 주입합니다. *"지난주에 바다 여행 가자고 했잖아"* — 캐릭터가 약속을 기억합니다.

### 🌿 분기형 내러티브 (Choice Cards)
대화 중 핵심 순간에 갈래길 선택지가 등장합니다. 선택지는 문장 그대로 전송되지 않고 **행동 지시**로 처리되어, AI가 그 행동이 일어난 직후의 장면을 이어 그립니다.

### 🎬 서사 일관성 엔진
- **개장 장면 고정**: 캐릭터의 첫 메시지가 세션 첫 턴에 히스토리로 고정되어, AI가 시작 위치·상황을 인식한 상태로 대화를 시작합니다.
- **장면 모순 방지**: 직전에 확정된 공간·시간·위치와 모순되는 전개(이미 실내에 도착했는데 갑자기 밖의 비 소식 등)를 금지하는 지시문이 프롬프트에 주입됩니다.
- **직전 행동 유지**: 캐릭터가 제안한 행동(앉으라는 대사 후 앉은 상태 유지 등)은 다음 턴에서도 이어집니다.

### 🌱 초기 설정 & 📝 유저 패치
| | 초기 설정 (제작자) | 유저 패치 (유저) |
|---|---|---|
| 작성 시점 | 카드 생성 시 | 채팅 중 언제든 (📝 버튼) |
| 길이 제한 | 1,000자 | 1,000자 |
| 지속 기간 | **약 20턴** 후 자연 소멸 (휘발성) | 무기한 상시 반영 |

초기 설정으로 도입부 분위기를 제어하면서도 유저의 자유도를 해치지 않고, 유저 패치로 진행된 서사·감정선·묘사 스타일("짧고 문학적으로" 등)을 지속적으로 지시할 수 있습니다.

### 🎨 Creator Studio
| 직접 만들기 | AI 어시스트 |
|---|---|
| 시스템 프롬프트, 첫 메시지, 태그, 장르, 초기 설정, 톤, 카드 색상을 모두 직접 설정 | **시스템 프롬프트 한 줄만 작성하면** 첫 메시지·태그·장르·소개글·예시 대화를 AI가 자동 완성 |

유저가 만든 모든 캐릭터에는 `커스텀` 태그가 자동으로 붙어 목록에서 구분됩니다(홈 필터의 `커스텀` 탭으로 한눈에 볼 수 있어요). 생성된 캐릭터는 언제든 삭제 API로 정리할 수 있습니다.

### ✏️ 캐릭터 수정 (제작자 전용)
자신이 만든 커스텀 캐릭터라면 언제든 수정할 수 있습니다. 상세 화면의 `✏️ 수정` 버튼으로 이름·시스템 프롬프트·첫 메시지·줄거리·세계관 등을 변경할 수 있고, 다른 사람의 카드나 공식 카드는 서버에서 403으로 차단합니다.

### 👤 계정 & 기기 간 동기화
닉네임과 비밀번호만으로 간단히 가입합니다(PBKDF2 해시 저장).

- **AI가 유저를 닉네임으로 부릅니다** — 프롬프트에 유저 이름이 주입됩니다.
- **세션 키 = `{닉네임}:{캐릭터ID}`** — 어느 기기에서 같은 계정으로 로그인해도 대화·감정 게이지·장기기억이 그대로 이어집니다.
- 대화 데이터는 계정별로 완전 격리되어, 다른 계정과 절대 섞이지 않습니다.
- 토큰 만료(30일) 시에는 자동 로그아웃 후 안내 배너와 함께 로그인 화면으로 이동하며, 재로그인하면 대화가 그대로 복구됩니다.

### 🗝️ 멀티 키 라운드로빈
`GOOGLE_API_KEY`, `GOOGLE_API_KEY_2`, `GOOGLE_API_KEY_3`… 형식으로 키를 무제한 추가할 수 있으며, 요청마다 Round Robin으로 순회합니다. 429 레이트리밋이 걸린 키는 **2분간 자동 쿨다운** 후 로테이션에 복귀하고, 5xx·네트워크 오류·무효 키는 즉시 다음 키로 폴백합니다.

```bash
python -m library.inference.key_cli list / add / remove   # 키 관리 CLI
```

## 🏗️ 아키텍처

```
[Client] React/Vite SPA (PC · 모바일 반응형)
    │  SSE 스트리밍 + REST (Bearer 토큰 인증)
[API] FastAPI
    │
    ├─ 인증             닉네임+비밀번호 (PBKDF2) · 토큰 발급/검증
    ├─ 감성 분류기 ──┐ (병렬)
    ├─ FSM 감정 엔진 ←┘   Redis 영속화 (미설정 시 인메모리)
    ├─ 세션 메타          초기 설정 스냅샷 · 유저 패치
    ├─ RAG 장기기억       임베딩 벡터 검색 (SQLite·Redis)
    ├─ 프롬프트 컴파일러   감정+기억+초기설정+패치+서사지시 주입
[AI Inference] Gemma 4 · Gemini 3.5 Flash Lite (사용자 선택, Gemini API)
    키 라운드로빈 · 429 쿨다운 · 폴백 재시도
```

**파이프라인 불변식:** 유저 발화 → 감성 분류 → FSM 커밋 → 기억 검색 → 프롬프트 주입(닉네임 포함) → **그 다음** 토큰 생성. 감정 상태는 반드시 생성 이전에 결정적으로 갱신됩니다.

## 📱 모바일 지원

- iOS Safari의 입력 자동 확대를 방지하고(입력 글자 16px), 키보드가 올라와도 **최신 대화가 입력창 위에 유지**됩니다.
- 세이프 에어리어(노치/홈바) 대응 및 터치 최적화가 적용되어 있습니다.

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
├── characters/methods/            # 기본 캐릭터 10종 + 커스텀 카드
├── library/
│   ├── api.py                     # FastAPI 라우팅 (chat/stream, auth, sessions, patch)
│   ├── auth/store.py              # 계정·토큰 저장소 (PBKDF2, Redis/메모리)
│   ├── fsm/
│   │   ├── engine.py              # 감정 벡터 FSM + 무드 도출
│   │   ├── session_meta.py        # 초기 설정 스냅샷 · 유저 패치 저장소
│   │   └── classifier.py          # 감성/의도 분류기
│   ├── inference/
│   │   ├── gemma_client.py        # Gemma 추론 (스트리밍, 키 폴백, 컨텍스트 초과 감지)
│   │   ├── key_manager.py         # 라운드로빈 키 풀 + 쿨다운
│   │   ├── prompt_compiler.py     # 동적 프롬프트 컴파일 (예산 관리 포함)
│   │   └── narrative.py           # Choice Card 생성
│   ├── memory/store.py            # RAG 장기기억(벡터) + 히스토리 영속화
│   └── creators/
│       ├── builder.py             # 캐릭터 카드 검증/저장/삭제 (커스텀 태그 자동 부여)
│       └── assist.py              # AI 어시스트 자동완성
├── web/src/                       # React SPA
│   ├── App.jsx                    # 라우팅·토큰 관리 셸
│   ├── AuthPage.jsx               # 로그인/회원가입 화면
│   ├── api.js                     # 공용 API 헬퍼 + 토큰 만료(401) 감지
│   ├── Home.jsx                   # 카드 그리드 (장르·커스텀 필터)
│   ├── CharacterDetail.jsx        # 줄거리·세계관·예시 대화
│   ├── Chat.jsx                   # SSE 채팅 + 모델 선택 + 유저 패치/기억/감정 패널
│   ├── EmotionGraph.jsx           # 감정 변화 그래프 (턴별 4차원)
│   ├── CreateCharacter.jsx        # 직접 만들기 / AI 어시스트
│   └── EditCharacter.jsx          # 커스텀 캐릭터 수정 (제작자 전용)
├── scripts/stress_test.py         # 길이 스트레스 테스트 스크립트
└── tests/                         # pytest (29개)
```

## 🔌 API 요약

| Method | Path | 설명 |
|---|---|---|
| `POST` | `/auth/register` | 닉네임+비밀번호 회원가입 (즉시 토큰 발급) |
| `POST` | `/auth/login` | 로그인 |
| `POST` | `/auth/logout` | 로그아웃 (토큰 폐기) |
| `GET` | `/characters` | 캐릭터 목록 |
| `POST` | `/characters` | 캐릭터 카드 직접 등록 |
| `POST` | `/characters/assist` | 시스템 프롬프트만으로 AI 캐릭터 생성 |
| `DELETE` | `/characters/{id}` | 캐릭터 삭제 |
| `GET` / `PUT` | `/characters/{id}` | 캐릭터 조회/수정 (제작자 전용, 공식 카드 403) |
| `POST` | `/chat` | 채팅 (일괄 응답) |
| `POST` | `/chat/stream` | 채팅 (SSE 스트리밍, `model` 필드로 모델 선택) |
| `GET` | `/models` | 사용 가능한 모델 목록 |
| `GET` | `/sessions/{id}/history` | 대화 복원 (+유저 패치) |
| `DELETE` | `/sessions/{id}` | 대화 초기화 (히스토리 + 장기기억 + 감정 그래프 모두 삭제) |
| `GET` / `PUT` | `/sessions/{id}/user-patch` | 유저 패치 조회/저장 |
| `GET` | `/sessions/{id}/emotions` | 감정 히스토리를 반환 (감정 그래프용) |
| `GET` / `DELETE` | `/sessions/{id}/memories[/{memory_id}]` | 장기기억 목록/개별 삭제 |
| `GET` | `/sessions/{id}/state` | 현재 FSM 상태 스냅샷 |
| `GET` | `/health` | 헬스 체크 |

## 🛣️ 로드맵

- [x] Redis 세션 저장소 (`REDIS_URL` 설정 시 FSM·히스토리·기억·카드 모두 영속화)
- [x] 임베딩 기반 벡터 검색 (text-embedding-004)
- [x] 듀얼 모델 지원 (Gemma 4 · Gemini 3.5 Flash Lite, 채팅 화면에서 전환)
- [ ] Milvus/Pinecone 전환 (대규모 운영용)
- [ ] React Native 모바일 앱

---

*Powered by Gemma 4 · Gemini 3.5 Flash Lite · FSM Emotion Engine · RAG Long-term Memory*