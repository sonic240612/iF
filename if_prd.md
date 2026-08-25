# 🚀 iF (이프) — AI Character & Interactive Narrative Platform PRD (v2.0 Enterprise)

## 1. Executive Summary & Vision
- **Product Name:** iF (이프)
- **Core Proposition:** 차원의 틈을 넘어 유저가 내러티브의 주체가 되어 캐릭터와 감정적으로 교류하는 **고(高)몰입 AI 스토리텔링 & 캐릭터 채팅 플랫폼**.
- **Market Positioning:** 일회성 소비형 챗봇의 한계를 극복하고, 유저 주도형 분기 전개(Branching Narrative)와 크리에이터 중심의 퍼블리싱 생태계를 결합한 하이브리드 플랫폼.

---

## 2. Technical Architecture & AI Pipeline
- **Client Layer:** React/Vite SPA (Web) & React Native (Mobile App) with WebSocket/SSE for real-time streaming.
- **Backend & API:** Node.js / FastAPI, Auth, Creator Studio Compiler, Billing Engine.
- **AI Inference:** 
  - **Model:** Gemma 최신 아키텍처 (저지연, 고성능 토큰 처리 최적화).
  - **State Engine (FSM):** Redis 기반 캐릭터별 [호감도, 집착도, 혐관 지수, 질투 게이지] 실시간 캐싱 및 동적 프롬프트 주입.
  - **RAG / Lorebook:** Milvus / Pinecone을 활용한 장기 기억 및 세계관 청킹(Chunking) 관리.

---

## 3. Core UX & Feature Specifications

### ① Interactive Branching Narrative Engine
- 대화 중 핵심 분기점에서 2~3개의 선택지(Choice Card) 제공 또는 유저 프리폼 입력에 즉각 반응하는 실시간 서사 생성.
- 타이프라이터 이펙트 및 감정 변화에 따른 다이내믹 UI 테마 시프트.

### ② Emotion & Dynamics Simulation
- 유저 발화 감성 분석을 통해 캐릭터의 내부 상태(State)를 갱신. (예: 냉정한 대답 -> 질투/집착 게이지 상승 및 츤데레 대사 가중치 부여)

### ③ Creator Studio & Tokenization Economy
- **No-Code Character Builder:** 기본 정보, 시스템 프롬프트, 첫 대사, 관계성 태그만으로 나만의 AI 캐릭터 제작.
- **Creator Revenue Share:** 캐릭터 이용량 및 토큰 소비량에 연동된 투명한 크리에이터 정산 시스템.

### ④ Hybrid Pricing Model
- **Freemium:** 일일 무료 크레딧 + 광고 리필 시스템.
- **Lowest-Cost Subscription:** 업계 최저가 무제한 구독 플랜 및 종량제 토큰 패키지 병행.

---

## 4. Product Metrics & KPIs
- **Engagement:** DAU/MAU 비율(Stickiness), 평균 세션 지속 시간(Average Session Duration).
- **Monetization:** 유료 전환율(CR), ARPU 및 ARPPU.
- **Creator Ecosystem:** 월간 신규 생성 캐릭터 수, 크리에이터 리텐션.
