"""RAG 장기기억 저장소.

구성:
  - 로컬: SQLite (data/memory.db)
  - 서버리스/Vercel(REDIS_URL + VERCEL=1): Redis 전용 모드 (읽기 전용 FS 회피)
  - 일반 서버 + REDIS_URL: Redis 우선 + SQLite 백업 이중 저장

프롬프트 불변식: 검색된 기억은 반드시 '토큰 생성 이전'에 프롬프트에 주입된다.
"""
from __future__ import annotations

import json
import math
import uuid
import os
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "memory.db"

SUMMARY_INTERVAL = 10   # N 어시스턴트 턴마다 요약 기억 생성
TOP_K = 3               # 매 턴 주입할 기억 개수
MEM_KEY_PREFIX = "if:mem:"
EMO_KEY_PREFIX = "if:emo:"          # 감정 변화 히스토리
HIST_KEY_PREFIX = "if:hist:"
MAX_MEMORIES = 200      # 세션당 유지할 기억 상한

_rc = None


def _redis():
    """REDIS_URL이 설정된 경우에만 Redis 클라이언트 반환, 아니면 None."""
    global _rc
    url = os.environ.get("REDIS_URL")
    if not url:
        return None
    if _rc is None:
        try:
            import redis
            _rc = redis.Redis.from_url(url, decode_responses=True, socket_timeout=3)
            _rc.ping()
            print("[memory] Redis 연결됨 — 기억/히스토리 영속화 활성화")
        except Exception as e:
            print(f"[memory] Redis 연결 실패, 로컬 스토어 폴백: {e}")
            return None
    return _rc


def _sqlite_ok() -> bool:
    """서버리스(읽기 전용 FS)에서는 SQLite를 사용하지 않는다."""
    return not (_rc or os.environ.get("VERCEL") == "1")


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS memories (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_id TEXT NOT NULL,
               turn INTEGER NOT NULL,
               text TEXT NOT NULL,
               embedding TEXT,
               created_at REAL NOT NULL
           )"""
    )
    try:  # 기존 DB 마이그레이션
        conn.execute("ALTER TABLE memories ADD COLUMN embedding TEXT")
    except sqlite3.OperationalError:
        pass
    return conn


SUMMARY_PROMPT = """아래는 유저와 캐릭터의 최근 대화다. 나중에 다시 참조할 수 있도록
핵심 사건/약속/감정 변화만 담아 한국어 한두 문장의 '기억'으로 정리하라.
설명 없이 기억 문장만 출력하라.

[대화]
{dialog}
"""


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[\s,.?!~\"'()\[\]{}:;]+", text) if len(t) >= 2}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def search_memories(session_id: str, query: str, k: int = TOP_K) -> list[str]:
    """현재 발화와 관련度 높은 과거 기억을 검색한다.

    1차: 임베딩 코사인 유사도 (의미 기반)
    폴백: 토큰 오버랩 스코어링 (임베딩 불가 시)
    """
    rows: list[tuple[str, str | None]] = []  # (text, embedding_json)
    r = _redis()
    if r:
        try:
            entries = r.lrange(MEM_KEY_PREFIX + session_id, -MAX_MEMORIES, -1)
            rows = [(e.get("text"), e.get("embedding")) for e in map(json.loads, entries)]
        except Exception as e:
            print(f"[memory] Redis 조회 실패: {e}")
    if not rows and _sqlite_ok():
        with _conn() as conn:
            rows = conn.execute(
                "SELECT text, embedding FROM memories WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, MAX_MEMORIES),
            ).fetchall()

    if not rows:
        return []

    q_tokens = _tokenize(query)

    # 1) 벡터 검색 시도
    q_emb = None
    try:
        from library.inference import gemma_client
        if any(r[1] for r in rows):  # 저장된 벡터가 하나라도 있을 때만 호출
            q_emb = gemma_client.embed(query)
    except Exception:
        q_emb = None

    if q_emb:
        scored = []
        for text, emb_json in rows:
            if not emb_json:
                continue
            sim = _cosine(q_emb, json.loads(emb_json))
            if sim > 0.5:
                scored.append((sim, text))
        if scored:
            scored.sort(key=lambda t: -t[0])
            return [text for _, text in scored[:k]]

    # 2) 폴백: 토큰 오버랩 + 부분 문자열 매칭 (한국어 조사 변화 대응)
    if not q_tokens:
        return []
    scored = []
    for text, _emb in rows:
        score = len(q_tokens & _tokenize(text))
        score += sum(1 for t in q_tokens if t in text and t not in _tokenize(text))
        if score > 0:
            scored.append((score, text))
    scored.sort(key=lambda t: -t[0])
    return [text for _, text in scored[:k]]


def save_memory(session_id: str, turn: int, text: str) -> bool:
    """기억 저장. 실제로 저장되었으면 True."""
    emb_json = None
    try:
        from library.inference import gemma_client
        emb = gemma_client.embed(text)
        if emb:
            emb_json = json.dumps(emb)
    except Exception:
        pass

    if _redis():
        try:
            mid = uuid.uuid4().hex[:12]
            entry = json.dumps({"id": mid, "turn": turn, "text": text.strip(), "embedding": emb_json}, ensure_ascii=False)
            r = _redis()
            pipe = r.pipeline()
            pipe.rpush(MEM_KEY_PREFIX + session_id, entry)
            pipe.ltrim(MEM_KEY_PREFIX + session_id, -MAX_MEMORIES, -1)
            pipe.expire(MEM_KEY_PREFIX + session_id, 60 * 60 * 24 * 30)  # 30일
            pipe.execute()
            return True
        except Exception as e:
            print(f"[memory] Redis 기억 저장 실패: {e}")
            return False

    if _sqlite_ok():
        with _conn() as conn:
            conn.execute(
                "INSERT INTO memories (session_id, turn, text, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, turn, text.strip(), emb_json, time.time()),
            )
            return True

    print("[memory] 저장 가능한 스토리지가 없어 기억을 폐기했습니다 (REDIS_URL 확인 권장)")
    return False


def summarize_and_store(session_id: str, turn: int, history: list[dict]) -> str | None:
    """최근 대화 윈도우를 요약해 장기기억으로 저장. 실패 시 조용히 건너뜀."""
    from library.inference import gemma_client  # 순환 임포트 회피

    dialog = "\n".join(
        f"{'유저' if m['role'] == 'user' else '캐릭터'}: {m['content']}"
        for m in history[-SUMMARY_INTERVAL:]
    )
    try:
        summary = gemma_client.generate(SUMMARY_PROMPT.format(dialog=dialog), mood="neutral")
        summary = summary.replace("\n", " ").strip()
        if summary:
            save_memory(session_id, turn, summary)
            return summary
    except Exception as e:  # 요약 실패가 본 대화를 막지 않도록
        print(f"[memory] summarize failed: {e}")
    return None


def maybe_summarize(session_id: str, turn: int, history: list[dict]) -> bool:
    """SUMMARY_INTERVAL턴마다 True를 반환하며 요약을 수행."""
    if turn > 0 and turn % SUMMARY_INTERVAL == 0 and len(history) >= 4:
        return summarize_and_store(session_id, turn, history) is not None
    return False


def list_memories(session_id: str) -> list[dict]:
    """세션의 모든 장기기억 목록 (최신순, [{id, text}])."""
    out = []
    r = _redis()
    if r:
        try:
            entries = r.lrange(MEM_KEY_PREFIX + session_id, -MAX_MEMORIES, -1)
            for e in entries:
                d = json.loads(e)
                out.append({"id": d.get("id") or _synth_id(d.get("text", "")), "text": d.get("text", "")})
            return out
        except Exception:
            pass
    if not _sqlite_ok():
        return []
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id, text FROM memories WHERE session_id = ? ORDER BY id DESC",
            (session_id,),
        ).fetchall()
    return [{"id": str(rid), "text": text} for rid, text in rows]


def _synth_id(text: str) -> str:
    """구형(Redis 무ID) 항목용 합성 ID — 텍스트 해시 기반."""
    import hashlib
    return "h" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def delete_memory(session_id: str, memory_id: str) -> bool:
    """개별 기억 삭제. Redis/SQLite 양쪽 경로 지원."""
    r = _redis()
    if r:
        try:
            key = MEM_KEY_PREFIX + session_id
            entries = r.lrange(key, 0, -1)
            kept = []
            removed = False
            for e in entries:
                d = json.loads(e)
                eid = d.get("id") or _synth_id(d.get("text", ""))
                if eid == memory_id:
                    removed = True
                    continue
                kept.append(e)
            if removed:
                pipe = r.pipeline()
                pipe.delete(key)
                for e in reversed([e for e in kept]):
                    # lrange는 최신순이므로 원래 순서 복원
                    pass
                # 원본 순서 유지가 중요하지 않으므로 kept 순서대로 재저장
                for e in kept:
                    pipe.rpush(key, e)
                pipe.execute()
            return removed
        except Exception as e:
            print(f"[memory] Redis 개별 삭제 실패: {e}")
    if not _sqlite_ok():
        return False
    try:
        with _conn() as conn:
            cur = conn.execute(
                "DELETE FROM memories WHERE session_id = ? AND id = ?",
                (session_id, int(memory_id)),
            )
            return cur.rowcount > 0
    except (ValueError, sqlite3.Error):
        return False


# ── 감정 변화 히스토리 (감정 그래프용) ──

def record_emotion(session_id: str, turn: int, state_dict: dict) -> None:
    """턴마다 감정 스냅샷을 기록. Redis 우선, 없으면 SQLite."""
    snap = {k: state_dict.get(k, 0) for k in ("affection", "obsession", "enmity", "jealousy")}
    r = _redis()
    if r:
        try:
            key = EMO_KEY_PREFIX + session_id
            pipe = r.pipeline()
            entry = {**snap, "turn": turn}
            pipe.rpush(key, json.dumps(entry, ensure_ascii=False))
            pipe.ltrim(key, -100, -1)
            pipe.expire(key, 60 * 60 * 24 * 90)
            pipe.execute()
        except Exception as e:
            print(f"[memory] 감정 기록 실패: {e}")
            return
    if not _sqlite_ok():
        return
    try:
        with _conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS emotion_history ("
                "session_id TEXT, turn INTEGER, affection REAL, obsession REAL,"
                "enmity REAL, jealousy REAL, created_at REAL)"
            )
            conn.execute(
                "INSERT INTO emotion_history VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, turn, snap["affection"], snap["obsession"],
                 snap["enmity"], snap["jealousy"], time.time()),
            )
    except Exception as e:
        print(f"[memory] 감정 기록(SQLite) 실패: {e}")


def get_emotion_history(session_id: str, limit: int = 50) -> list[dict]:
    """감정 변화 히스토리 반환 (turn 순 오름차순)."""
    r = _redis()
    if r:
        try:
            entries = r.lrange(EMO_KEY_PREFIX + session_id, -limit, -1)
            out = []
            for e in entries:
                d = json.loads(e)
                d.setdefault("affection", 0)
                for k in ("affection", "obsession", "enmity", "jealousy", "turn"):
                    d[k] = float(d.get(k, 0))
                out.append(d)
            return out
        except Exception as e:
            print(f"[memory] Redis 감정 조회 실패: {e}")
    if not _sqlite_ok():
        return []
    try:
        with _conn() as conn:
            rows = conn.execute(
                "SELECT turn, affection, obsession, enmity, jealousy FROM emotion_history "
                "WHERE session_id = ? ORDER BY turn ASC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        keys = ["turn", "affection", "obsession", "enmity", "jealousy"]
        return [dict(zip(keys, row)) for row in rows]
    except Exception:
        return []


def count_memories(session_id: str | None = None) -> int:
    r = _redis()
    if r and session_id:
        try:
            return int(r.llen(MEM_KEY_PREFIX + session_id) or 0)
        except Exception:
            pass
    if not _sqlite_ok():
        return 0
    with _conn() as conn:
        if session_id:
            row = conn.execute("SELECT COUNT(*) FROM memories WHERE session_id=?", (session_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
    return row[0]


# ── 대화 히스토리 영속화 ──

def load_history(session_id: str) -> list[dict]:
    r = _redis()
    if r:
        try:
            raw = r.get(HIST_KEY_PREFIX + session_id)
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            print(f"[memory] Redis 히스토리 조회 실패: {e}")
    if not _sqlite_ok():
        return []
    with _conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS histories (session_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        row = conn.execute("SELECT data FROM histories WHERE session_id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else []


def save_history(session_id: str, history: list[dict]) -> None:
    if _redis():
        try:
            _redis().set(HIST_KEY_PREFIX + session_id, json.dumps(history, ensure_ascii=False))
        except Exception as e:
            print(f"[memory] Redis 히스토리 저장 실패: {e}")
    if not _sqlite_ok():
        return
    with _conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS histories (session_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        conn.execute(
            "INSERT INTO histories (session_id, data, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(session_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (session_id, json.dumps(history, ensure_ascii=False), time.time()),
        )


def delete_history(session_id: str) -> None:
    """대화 초기화: 히스토리 + 장기기억 모두 삭제."""
    if _redis():
        try:
            _redis().delete(MEM_KEY_PREFIX + session_id, HIST_KEY_PREFIX + session_id)
        except Exception as e:
            print(f"[memory] Redis 삭제 실패: {e}")
    if not _sqlite_ok():
        return
    with _conn() as conn:
        conn.execute("DELETE FROM memories WHERE session_id=?", (session_id,))
        conn.execute(
            "CREATE TABLE IF NOT EXISTS histories (session_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        conn.execute("DELETE FROM histories WHERE session_id=?", (session_id,))
