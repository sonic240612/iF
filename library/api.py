"""iF API 서버 (FastAPI).

파이프라인 불변식:
  유저 발화 → 감성 분류(병렬) → FSM 상태 커밋 → 동적 프롬프트 컴파일 → Gemma 추론
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import tomllib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from library.creators import assist as creator_assist
from library.creators import builder
from library.fsm import classifier
from library.fsm.engine import engine as fsm
from library.inference import gemma_client, narrative
from library.inference.prompt_compiler import compile_prompt
from library.memory import store as memory_store

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "configs" / "base.toml", "rb") as f:
    CONFIG = tomllib.load(f)

app = FastAPI(title="iF API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def strip_api_prefix(request, call_next):
    """프론트엔드는 /api/... 로 호출하고 실제 라우트는 /... 이다.
    프로덕션 단일 호스트(Vercel/Render)에서 접두사를 벗겨 라우팅한다."""
    path = request.scope.get("path", "")
    if path == "/api":
        request.scope["path"] = "/"
    elif path.startswith("/api/"):
        request.scope["path"] = path[len("/api"):]
    return await call_next(request)


# session_id -> [{"role", "content"}]
_histories: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    character_id: str
    message: str = Field(default="", max_length=2000)
    session_id: str
    action: str = Field(default="", max_length=300)  # 선택지 행동 (message와 2진 1)

    def effective_message(self) -> str:
        return (self.action or self.message).strip()


class ChatResponse(BaseModel):
    reply: str
    mood: str
    state: dict
    intent: str
    choice_cards: list[dict]


class CharacterCardRequest(BaseModel):
    id: str
    name: str
    system_prompt: str
    first_message: str
    tags: list[str]
    greeting_mood: str = "neutral"
    genre: str = "romance"
    emoji: str = "💬"
    gradient: str = "linear-gradient(135deg, #7aa2f7, #b060ff)"
    intro: str = ""
    worldview: str = ""
    example_dialogs: list[dict] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/characters")
def characters() -> list[dict]:
    # 목록에는 상세 대화 제외 (가벼운 페이로드)
    return [
        {k: v for k, v in c.items() if k != "example_dialogs"}
        for c in builder.list_characters()
    ]


@app.get("/characters/{character_id}")
def character_detail(character_id: str) -> dict:
    char = builder.load_character(character_id)
    if char is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    return char


@app.post("/characters")
def create_character(req: CharacterCardRequest) -> dict:
    try:
        return builder.save_card(req.model_dump())
    except builder.ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


class AssistRequest(BaseModel):
    system_prompt: str = Field(min_length=10, max_length=4000)
    name: str = Field(default="", max_length=40)


@app.post("/characters/assist")
def ai_assist_character(req: AssistRequest) -> dict:
    """시스템 프롬프트만으로 나머지 필드를 AI가 자동 생성"""
    try:
        return creator_assist.generate_card(req.system_prompt, req.name)
    except creator_assist.AssistError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 생성 실패: {e}")


@app.get("/sessions/{session_id}/history")
def get_history(session_id: str) -> dict:
    """재접속 시 이전 대화 복원용."""
    history = memory_store.load_history(session_id)
    state = fsm.get(session_id) if fsm.exists(session_id) else None
    return {"messages": history, "state": state.to_dict() if state else None}


@app.delete("/sessions/{session_id}")
def reset_session(session_id: str) -> dict:
    """대화 초기화: 히스토리 + FSM 상태 + 장기기억 삭제."""
    _histories.pop(session_id, None)
    fsm.pop(session_id)
    memory_store.delete_history(session_id)
    return {"status": "reset"}


def _prepare_chat(req: ChatRequest):
    """공통 파이프라인 (생성 이전 단계): 검증→감성분류→FSM 커밋→프롬프트 컴파일.
    불변식: FSM 상태 갱신과 기억 주입은 반드시 토큰 생성 전에 완료."""
    character = builder.load_character(req.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character not found: {req.character_id}")
    history = memory_store.load_history(req.session_id) or _histories.setdefault(req.session_id, [])
    _histories[req.session_id] = history
    intent_result = classifier.classify(req.effective_message())
    decay = CONFIG["fsm"].get("decay_per_turn", 0.0)
    state = fsm.commit(req.session_id, intent_result.delta, decay=decay)
    memories = memory_store.search_memories(req.session_id, req.effective_message())
    prompt = compile_prompt(
        character, state, history, req.message,
        long_term_memories=memories,
        user_action=req.action or None,
    )
    return character, history, intent_result, state, prompt, memories


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE 스트리밍 채팅.
    이벤트: state(FSM) → delta(토큰)* → done(선택지+기억여부) → error?"""
    try:
        character, history, intent_result, state, prompt, memories = _prepare_chat(req)
    except HTTPException as e:
        def err():
            yield _sse({"type": "error", "detail": e.detail})
        return StreamingResponse(err(), media_type="text/event-stream")

    mood = state.mood()

    def event_stream():
        gemma_client.reset_finish_state()
        # 1) 상태 먼저 전송 — UI가 감정 테마를 즉시 시프트
        yield _sse({
            "type": "state",
            "mood": mood,
            "state": state.to_dict(),
            "intent": intent_result.intent,
            "memories_injected": len(memories),
        })
        full_text_parts = []
        try:
            for delta in gemma_client.generate_remote_stream(prompt):
                full_text_parts.append(delta)
                if delta:
                    yield _sse({"type": "delta", "text": delta})
        except Exception as e:
            yield _sse({"type": "error", "detail": str(e)})
            return
        reply = "".join(full_text_parts).strip()
        user_entry = req.action or req.message
        history.append({"role": "user", "content": user_entry})
        history.append({"role": "assistant", "content": reply})
        memory_store.save_history(req.session_id, history)
        cards = narrative.build_choice_cards(intent_result, mood)
        summarized = memory_store.maybe_summarize(req.session_id, state.turn, history)
        yield _sse({
            "type": "done",
            "reply": reply,
            "choice_cards": cards,
            "memory_saved": summarized is not None,
            "total_memories": memory_store.count_memories(req.session_id),
            "truncated": gemma_client.was_truncated(),
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    character = builder.load_character(req.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character not found: {req.character_id}")

    history = memory_store.load_history(req.session_id) or _histories.setdefault(req.session_id, [])
    _histories[req.session_id] = history

    # 1) 감성 분류 (메인 요청과 병렬 실행 지점)
    intent_result = classifier.classify(req.effective_message())

    # 2) FSM 상태 갱신 — 반드시 생성 이전에 결정적으로 커밋
    decay = CONFIG["fsm"].get("decay_per_turn", 0.0)
    state = fsm.commit(req.session_id, intent_result.delta, decay=decay)

    # 2.5) 장기기억 검색(RAG) — 생성 이전에 프롬프트에 주입
    memories = memory_store.search_memories(req.session_id, req.effective_message())

    # 3) 동적 프롬프트 주입 후 추론
    prompt = compile_prompt(
        character, state, history, req.message,
        long_term_memories=memories,
        user_action=req.action or None,
    )
    reply = gemma_client.generate(prompt, mood=state.mood())

    # 4) 분기 선택지 생성
    cards = narrative.build_choice_cards(intent_result, state.mood())

    history.append({"role": "user", "content": req.action or req.message})
    history.append({"role": "assistant", "content": reply})
    memory_store.save_history(req.session_id, history)

    # 장기기억: 일정 턴마다 대화 요약 저장
    memory_store.maybe_summarize(req.session_id, state.turn, history)

    return ChatResponse(
        reply=reply,
        mood=state.mood(),
        state=state.to_dict(),
        intent=intent_result.intent,
        choice_cards=cards,
    )


@app.get("/sessions/{session_id}/state")
def session_state(session_id: str) -> dict:
    if not fsm.exists(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return fsm.get(session_id).to_dict()

@app.get("/debug")
def debug_bundle() -> dict:
    """배포 진단용: 서버리스 함수 내부에서 실제 파일들이 어디에 있는지 표시."""
    import sys

    def peek(p: Path):
        try:
            return {"path": str(p), "exists": p.exists(),
                    "children": [c.name for c in p.iterdir()][:20] if p.is_dir() else None}
        except Exception as e:
            return {"path": str(p), "error": str(e)}

    return {
        "cwd": str(Path.cwd()),
        "python": sys.version.split()[0],
        "root": peek(ROOT),
        "root_characters": peek(ROOT / "characters"),
        "root_configs_base": peek(ROOT / "configs" / "base.toml"),
        "task_root": peek(Path("/").anchor + "var/task" if Path("/var/task").exists() else Path.cwd()),
        "env_keys_present": sorted(
            k for k in ("GOOGLE_API_KEY", "GOOGLE_API_KEY_2", "GOOGLE_API_KEY_3", "REDIS_URL", "VERCEL")
            if os.environ.get(k)
        ),
    }


# ── /api 접두사 이중 라우트 (서버리스 플랫폼의 리라이트 경로 처리 차이 대응) ──
# 미들웨어가 /api를 벗겨주지만, 일부 플랫폼은 원본 경로를 그대로 전달하므로
# 양쪽 모두에서 라우트가 매칭되도록 /api/* 복제본을 정적 마운트보다 앞에 등록한다.
from starlette.routing import Route as _StarletteRoute


def _register_api_prefixed_duplicates() -> None:
    extras = []
    for route in app.router.routes:
        if isinstance(route, _StarletteRoute) and not route.path.startswith("/api"):
            extras.append(_StarletteRoute(
                "/api" + route.path,
                endpoint=route.endpoint,
                methods=route.methods,
                name=route.name + "_api_prefixed",
                include_in_schema=False,
            ))
    app.router.routes.extend(extras)


_register_api_prefixed_duplicates()

# ── 정적 SPA 서빙 (배포: web/dist가 있으면 단일 서비스로 운영) ──
_DIST = ROOT / "web" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
