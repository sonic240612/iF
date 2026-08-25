# iF — Technical Guide & CLAUDE.md

This file provides architectural guidance and engineering specifications for developers, AI prompt engineers, and system architects working on the **iF (이프)** high-immersion AI character chat and interactive narrative platform.

## Project Overview

**iF** is a next-generation AI character chat and branching narrative platform (spiritual successor and evolution of modern character chat experiences). It bridges the gap between static one-off AI chat and deep interactive storytelling. Powered by state-of-the-art **Gemma** models, iF features dynamic choice-driven branching stories, real-time emotion/affection state tracking (FSM), multi-genre catalogs (dating, wuxia, RPG, dark/obsession plots), and a no-code Creator Studio with tokenized revenue sharing.

## Setup & Local Development

```bash
uv sync                    # Install Python dependencies (Python 3.11+)
npm install                # Install frontend dependencies (React + Vite)
make setup                 # Initialize local environment & database migrations
make dev                   # Run full-stack local development server (API + Web SPA)
```

Both `make` (Unix) and `python tasks.py` (cross-platform) work. **`tasks.py` is the source of truth** for all build, test, and preprocessing pipelines.

---

## Architecture & System Topology

```
[Client Layer] 
  - React / Vite SPA (Web) & React Native (Mobile)
  - WebSocket / SSE for real-time streaming chat & typewriter effect
       │
[API Gateway & Load Balancer]
       │
[Application Server (FastAPI / Node.js)]
  ├── Auth & Session Manager
  ├── Creator Studio (Character Card Compiler & Validator)
  └── Monetization / Billing Engine (Stripe / In-App Purchases)
       │
[AI & State Orchestration Layer]
  ├── Gemma Model Inference Cluster (vLLM / TensorRT-LLM optimized)
  ├── FSM Emotion & Relationship State Engine (Redis backed)
  └── Vector DB / Lorebook RAG (Milvus / Pinecone for long-term memory)
```

### Key Subpackages (`library/`)
- `library/auth/`: User authentication and session token verification.
- `library/inference/`: Streaming generation request builder (`GenerationRequest`), LLM prompt compiler.
- `library/fsm/`: Finite State Machine governing character emotional states (Affection, Obsession, Enmity, Jealousy).
- `library/creators/`: Character card parsing, YAML/JSON schema validation, and publishing pipeline.
- `library/runtime/`: Device offloading, async task queue (Celery/Redis), and daemon manager.

---

## Critical Invariants & Engineering Rules

### 1. FSM State Synchronization
The chat engine maintains a real-time state tuple per user-character session: `[Affection, Obsession, Enmity, Jealousy]` (bounded `[0.0, 100.0]`). 
- **Rule:** Every user utterance passes through a lightweight sentiment/intent classifier (`library/fsm/classifier.py`) in parallel with the main LLM request. The resulting delta is committed to Redis and injected into the dynamic system prompt before the Gemma inference pass.
- **Gotcha:** Never modify FSM state post-generation; state mutation must be deterministic and precede token generation to ensure the character's tone matches its internal emotional vector.

### 2. Context Window & Lorebook RAG
- **Rule:** Long-running chat sessions exceed standard context limits. iF uses **Semantic Chunking & RAG** (`library/rag/`) to retrieve relevant character lore, past summary checkpoints, and key user-character milestones.
- **Gotcha:** Do not dump raw chat logs into the prompt. Always summarize historical windows every 50 turns and store them in the vector database.

### 3. Creator Studio Schema Compliance
- User-created characters must adhere to strict JSON Schema definitions (`configs/schemas/character_card.json`).
- **Rule:** Any character missing core attributes (`system_prompt`, `first_message`, `tags`) is rejected at the API gateway level before hitting the database.

---

## Config Flow & Presets

Config-driven via a tiered merge chain: `base.toml → presets.toml[<preset>] → characters/methods/<slug>.toml → CLI/API overrides`.

- `configs/base.toml`: Global platform defaults (default model endpoint, max token limits, rate limits, default freemium credit caps).
- `configs/presets.toml`: Hardware & latency profiles (`[production_gpu]`, `[low_latency]`, `[edge_inference]`).
- `configs/characters/`: Self-contained character archetype configs and official starter personas.

---

## Core Features & Modules

| Module | Purpose | Key File / Pointer |
|---|---|---|
| **Branching Narrative Engine** | Generates dynamic choice cards (Choice Cards) or free-form narrative continuations based on user input. | `library/inference/narrative.py` |
| **Emotion FSM** | Tracks live affection, obsession, and hostility vectors to dynamically shift AI tone and dialogue weights. | `library/fsm/engine.py` |
| **Creator Studio** | No-code character builder allowing users to define worldviews, prompts, and dialogue few-shots. | `library/creators/builder.py` |
| **Hybrid Billing** | Freesheet daily credit refill + lowest-cost subscription / token pack micro-transactions. | `library/billing/` |

---

## Programmatic API (SDK)

`iF` exposes a clean programmatic Python SDK for external integrations and automated bot testing:

```python
from if_sdk import Client, GenerationRequest

client = Client(api_key="***")
response = client.chat(
    character_id="char_alice_01",
    message="너 오늘 왜 이렇게 차갑게 구는 거야?",
    session_id="sess_99283"
)
print(response.text, response.current_state)
```

---

## Contributing & Development Workflow

1. **Tests:** Run unit tests via `pytest` before submitting PRs.
2. **Linting:** `ruff check . --fix && ruff format .` is strictly enforced on all modified files.
3. **Docs:** Any change to core FSM logic or prompt compilation must update the corresponding deep-dive under `docs/`.
