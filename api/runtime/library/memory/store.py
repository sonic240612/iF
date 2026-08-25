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


def save_memory(session_id: str, turn: int, text: str) -> None:
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
            entry = json.dumps({"turn": turn, "text": text.strip(), "embedding": emb_json}, ensure_ascii=False)
            r = _redis()
            pipe = r.pipeline()
            pipe.rpush(MEM_KEY_PREFIX + session_id, entry)
            pipe.ltrim(MEM_KEY_PREFIX + session_id, -MAX_MEMORIES, -1)
            pipe.expire(MEM_KEY_PREFIX + session_id, 60 * 60 * 24 * 30)  # 30일
            pipe.execute()
            return
        except Exception as e:
            print(f"[memory] Redis 기억 저장 실패: {e}")

    if _sqlite_ok():
        with _conn() as conn:
            conn.execute(
                "INSERT INTO memories (session_id, turn, text, embedding, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, turn, text.strip(), emb_json, time.time()),
            )


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
