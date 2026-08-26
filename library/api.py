"""iF API 서버 (FastAPI).

파이프라인 불변식:
  유저 발화 → 감성 분류(병렬) → FSM 상태 커밋 → 동적 프롬프트 컴파일 → Gemma 추론
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import tomllib
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from library.creators import assist as creator_assist
from library.creators import builder
from library.fsm import classifier
from library.auth import store as auth_store
from library.fsm import session_meta
from library.fsm.engine import engine as fsm
from library.inference import gemma_client, narrative
from library.inference.prompt_compiler import compile_prompt
from library.memory import store as memory_store

ROOT = Path(__file__).resolve().parents[1]
with open(ROOT / "configs" / "base.toml", "rb") as f:
    CONFIG = tomllib.load(f)

app = FastAPI(title="iF API", version="0.1.0")
_ALLOWED_ORIGINS = CONFIG.get("cors", {}).get(
    "allowed_origins",
    ["https://if-chat-plum.vercel.app", "http://localhost:5173"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
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



import re as _re

# 모델이 프롬프트의 메타 블록을 흉내내서 출력하는 것을 제거
_META_LINE_RE = _re.compile(
    r"^\[(?:현재 감정 상태|말투 지시|초기 설정|유저 패치|과거 기억|서사 진행 지시|"
    r"유저가 선택한 행동|출력 규칙)\][^\n]*\n?",
    _re.M,
)


def sanitize_reply(text: str) -> str:
    """응답에서 메타 블록 라인 제거 + 과도한 개행 정리."""
    if not text:
        return text
    cleaned = _META_LINE_RE.sub("", text)
    cleaned = _re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _bearer_token(request: Request) -> str:
    authz = request.headers.get("authorization", "")
    return authz[7:].strip() if authz.lower().startswith("bearer ") else ""


def current_user(request: Request) -> str:
    user = auth_store.user_for_token(_bearer_token(request))
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user


def session_key(user: str, character_id: str) -> str:
    """유저별 세션 키 — 어느 기기에서 접속해도 같은 대화가 이어지도록 결정적 생성."""
    return f"{user}:{character_id}"


# session_id -> [{"role", "content"}]
_histories: dict[str, list[dict]] = {}


class ChatRequest(BaseModel):
    character_id: str
    message: str = Field(default="", max_length=2000)
    session_id: str = ""
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
    system_prompt: str = Field(max_length=4_000_000)
    first_message: str
    tags: list[str]
    greeting_mood: str = "neutral"
    genre: str = "romance"
    emoji: str = "💬"
    gradient: str = "linear-gradient(135deg, #7aa2f7, #b060ff)"
    intro: str = ""
    worldview: str = ""
    initial_setup: str = Field(default="", max_length=1000)
    example_dialogs: list[dict] = []


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# ── 인증 (닉네임 + 비밀번호) ──
class AuthRequest(BaseModel):
    nickname: str = Field(min_length=2, max_length=20)
    password: str = Field(min_length=6, max_length=64)


@app.post("/auth/register")
def register(req: AuthRequest) -> dict:
    """닉네임+비밀번호로 가입. 성공 시 즉시 로그인(토큰 발급)."""
    try:
        token = auth_store.create_user(req.nickname, req.password)
    except auth_store.NicknameTakenError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except auth_store.ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"token": token, "nickname": req.nickname.strip()}


@app.post("/auth/login")
def login(req: AuthRequest) -> dict:
    try:
        token = auth_store.login(req.nickname, req.password)
    except auth_store.InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))
    return {"token": token, "nickname": req.nickname.strip()}


@app.post("/auth/logout")
def logout(request: Request, user: str = Depends(current_user)) -> dict:
    auth_store.revoke_token(_bearer_token(request))
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
def create_character(req: CharacterCardRequest, user: str = Depends(current_user)) -> dict:
    try:
        return builder.save_card(req.model_dump(), creator=user)
    except builder.ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))


class AssistRequest(BaseModel):
    system_prompt: str = Field(min_length=10, max_length=4000)
    name: str = Field(default="", max_length=40)


@app.post("/characters/assist")
def ai_assist_character(req: AssistRequest, user: str = Depends(current_user)) -> dict:
    """시스템 프롬프트만으로 나머지 필드를 AI가 자동 생성"""
    try:
        return creator_assist.generate_card(req.system_prompt, req.name, creator=user)
    except creator_assist.AssistError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI 생성 실패: {e}")


@app.delete("/characters/{character_id}")
def delete_character(character_id: str, user: str = Depends(current_user)) -> dict:
    """캐릭터 카드 삭제."""
    if builder.load_character(character_id) is None:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    builder.delete_card(character_id)
    return {"status": "deleted", "id": character_id}


class EditCharacterRequest(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    system_prompt: str | None = Field(default=None, max_length=4_000_000)
    first_message: str | None = Field(default=None, max_length=4000)
    tags: list[str] | None = None
    greeting_mood: str | None = None
    genre: str | None = Field(default=None, max_length=30)
    emoji: str | None = Field(default=None, max_length=8)
    gradient: str | None = Field(default=None, max_length=200)
    intro: str | None = Field(default=None, max_length=2000)
    worldview: str | None = Field(default=None, max_length=2000)
    initial_setup: str | None = Field(default=None, max_length=1000)
    example_dialogs: list[dict] | None = None


@app.put("/characters/{character_id}")
def edit_character(character_id: str, req: EditCharacterRequest, user: str = Depends(current_user)) -> dict:
    """캐릭터 카드 부분 수정 — 제작자 본인만 가능."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    try:
        return builder.update_card(character_id, updates, user=user)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"character not found: {character_id}")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except builder.ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))



@app.get("/sessions/{session_id}/memories")
def list_session_memories(session_id: str, user: str = Depends(current_user)) -> dict:
    """장기기억 목록 조회 (기억 관리 패널용)."""
    skey = session_key(user, session_id)
    return {"memories": memory_store.list_memories(skey)}


@app.delete("/sessions/{session_id}/memories/{memory_id}")
def remove_session_memory(session_id: str, memory_id: str, user: str = Depends(current_user)) -> dict:
    ok = memory_store.delete_memory(session_key(user, session_id), memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="memory not found")
    return {"status": "deleted", "total_memories": memory_store.count_memories(skey := session_key(user, session_id))}


@app.get("/sessions/{session_id}/history")
def get_history(session_id: str, user: str = Depends(current_user)) -> dict:
    """재접속 시 이전 대화 복원용 (유저별 격리)."""
    skey = session_key(user, session_id)
    history = memory_store.load_history(skey)
    state = fsm.get(skey) if fsm.exists(skey) else None
    return {
        "messages": history,
        "state": state.to_dict() if state else None,
        "user_patch": session_meta.get_meta(skey).get("user_patch", ""),
    }


class UserPatchRequest(BaseModel):
    patch: str = Field(default="", max_length=1000)


@app.get("/sessions/{session_id}/emotions")
def get_emotions(session_id: str, user: str = Depends(current_user)) -> dict:
    """감정 변화 히스토리 (그래프용)."""
    skey = session_key(user, session_id)
    return {"history": memory_store.get_emotion_history(skey)}


@app.get("/sessions/{session_id}/user-patch")
def get_user_patch(session_id: str, user: str = Depends(current_user)) -> dict:
    skey = session_key(user, session_id)
    return {"patch": session_meta.get_meta(skey).get("user_patch", "")}


@app.put("/sessions/{session_id}/user-patch")
def set_user_patch(session_id: str, req: UserPatchRequest, user: str = Depends(current_user)) -> dict:
    skey = session_key(user, session_id)
    session_meta.set_user_patch(skey, req.patch)
    return {"status": "ok", "patch": (req.patch or "").strip()[:1000]}


@app.delete("/sessions/{session_id}")
def reset_session(session_id: str, user: str = Depends(current_user)) -> dict:
    """대화 초기화: 히스토리 + FSM 상태 + 장기기억 + 세션 메타 삭제."""
    skey = session_key(user, session_id)
    _histories.pop(skey, None)
    fsm.pop(skey)
    memory_store.delete_history(skey)
    session_meta.delete(skey)
    return {"status": "reset"}


def _prepare_chat(req: ChatRequest, user: str):
    """공통 파이프라인 (생성 이전 단계): 검증→감성분류→FSM 커밋→프롬프트 컴파일.
    불변식: FSM 상태 갱신과 기억 주입은 반드시 토큰 생성 전에 완료."""
    character = builder.load_character(req.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character not found: {req.character_id}")
    skey = session_key(user, req.character_id)
    history = memory_store.load_history(skey) or _histories.setdefault(skey, [])
    _histories[skey] = history
    # 첫 턴: 첫 메시지를 '개장 장면'으로 히스토리에 고정 → 모델이 시작 상황을 인식함
    if not history and character.get("first_message"):
        history.append({"role": "assistant", "content": character["first_message"]})
    intent_result = classifier.classify(req.effective_message())
    decay = CONFIG["fsm"].get("decay_per_turn", 0.0)
    state = fsm.commit(skey, intent_result.delta, decay=decay)
    memory_store.record_emotion(skey, state.turn,
        {"affection": state.affection, "obsession": state.obsession,
         "enmity": state.enmity, "jealousy": state.jealousy})
    memories = memory_store.search_memories(skey, req.effective_message())
    # 세션 시작 시 초기 설정 스냅샷 (이미 있으면 기존 값 유지)
    meta = session_meta.init_if_absent(skey, character.get("initial_setup", ""))
    prompt = compile_prompt(
        character, state, history, req.message,
        long_term_memories=memories,
        user_action=req.action or None,
        initial_setup=meta.get("initial_setup"),
        user_patch=meta.get("user_patch"),
        user_nickname=user,
    )
    return character, history, intent_result, state, prompt, memories


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/chat/stream")
def chat_stream(req: ChatRequest, user: str = Depends(current_user)):
    """SSE 스트리밍 채팅 (유저별 세션).
    이벤트: state(FSM) → delta(토큰)* → done(선택지+기억여부) → error?"""
    try:
        character, history, intent_result, state, prompt, memories = _prepare_chat(req, user)
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
        except gemma_client.ContextOverflowError as e:
            yield _sse({"type": "error", "detail": str(e) + " (시스템 프롬프트가 너무 깁니다 — base.toml의 system_prompt_max_chars 조정 가능)"})
            return
        except Exception as e:
            yield _sse({"type": "error", "detail": str(e)})
            return
        reply = sanitize_reply("".join(full_text_parts).strip())
        user_entry = req.action or req.message
        history.append({"role": "user", "content": user_entry})
        history.append({"role": "assistant", "content": reply})
        memory_store.save_history(session_key(user, req.character_id), history)
        cards = narrative.build_choice_cards(intent_result, mood)
        summarized = memory_store.maybe_summarize(session_key(user, req.character_id), state.turn, history)
        yield _sse({
            "type": "done",
            "reply": reply,
            "choice_cards": cards,
            "memory_saved": summarized is not None,
            "total_memories": memory_store.count_memories(session_key(user, req.character_id)),
            "truncated": gemma_client.was_truncated(),
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: str = Depends(current_user)) -> ChatResponse:
    character = builder.load_character(req.character_id)
    if character is None:
        raise HTTPException(status_code=404, detail=f"character not found: {req.character_id}")

    skey = session_key(user, req.character_id)
    history = memory_store.load_history(skey) or _histories.setdefault(skey, [])
    _histories[skey] = history
    # 첫 턴: 첫 메시지를 '개장 장면'으로 히스토리에 고정
    if not history and character.get("first_message"):
        history.append({"role": "assistant", "content": character["first_message"]})

    # 1) 감성 분류 (메인 요청과 병렬 실행 지점)
    intent_result = classifier.classify(req.effective_message())

    # 2) FSM 상태 갱신 — 반드시 생성 이전에 결정적으로 커밋
    decay = CONFIG["fsm"].get("decay_per_turn", 0.0)
    state = fsm.commit(skey, intent_result.delta, decay=decay)
    # 감정 변화 기록 (그래프용)
    memory_store.record_emotion(skey, state.turn,
        {"affection": state.affection, "obsession": state.obsession,
         "enmity": state.enmity, "jealousy": state.jealousy})

    # 2.5) 장기기억 검색(RAG) — 생성 이전에 프롬프트에 주입
    memories = memory_store.search_memories(skey, req.effective_message())

    meta = session_meta.init_if_absent(skey, character.get("initial_setup", ""))
    # 3) 동적 프롬프트 주입 후 추론
    prompt = compile_prompt(
        character, state, history, req.message,
        long_term_memories=memories,
        user_action=req.action or None,
        initial_setup=meta.get("initial_setup"),
        user_patch=meta.get("user_patch"),
        user_nickname=user,
    )
    try:
        reply = sanitize_reply(gemma_client.generate(prompt, mood=state.mood()))
    except gemma_client.ContextOverflowError as e:
        raise HTTPException(status_code=413, detail=str(e))

    # 4) 분기 선택지 생성
    cards = narrative.build_choice_cards(intent_result, state.mood())

    history.append({"role": "user", "content": req.action or req.message})
    history.append({"role": "assistant", "content": reply})
    memory_store.save_history(skey, history)

    # 장기기억: 일정 턴마다 대화 요약 저장
    memory_store.maybe_summarize(skey, state.turn, history)

    return ChatResponse(
        reply=reply,
        mood=state.mood(),
        state=state.to_dict(),
        intent=intent_result.intent,
        choice_cards=cards,
    )


@app.get("/sessions/{session_id}/state")
def session_state(session_id: str, user: str = Depends(current_user)) -> dict:
    skey = session_key(user, session_id)
    if not fsm.exists(skey):
        raise HTTPException(status_code=404, detail="session not found")
    return fsm.get(skey).to_dict()

# ── 정적 SPA 서빙 (배포: web/dist가 있으면 단일 서비스로 운영) ──
_DIST = ROOT / "web" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
