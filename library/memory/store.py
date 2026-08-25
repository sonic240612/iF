"""RAG 장기기억 저장소.

MVP 구성:
  - 저장: SQLite (data/memory.db) — 운영 시 Milvus/Pinecone으로 교체되는 지점
  - 요약: SUMMARY_INTERVAL턴마다 대화 윈도우를 Gemma로 요약해 기억으로 저장
  - 검색: 토큰 오버랩 스코어링(경량 BM25 성격)으로 현재 발화와 관련된 기억 top-k 주입

프롬프트 불변식: 검색된 기억은 반드시 '토큰 생성 이전'에 프롬프트에 주입된다.
"""
from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "memory.db"

SUMMARY_INTERVAL = 10   # N 어시스턴트 턴마다 요약 기억 생성
TOP_K = 3               # 매 턴 주입할 기억 개수


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS memories (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_id TEXT NOT NULL,
               turn INTEGER NOT NULL,
               text TEXT NOT NULL,
               created_at REAL NOT NULL
           )"""
    )
    return conn


SUMMARY_PROMPT = """아래는 유저와 캐릭터의 최근 대화다. 나중에 다시 참조할 수 있도록
핵심 사건/약속/감정 변화만 담아 한국어 한두 문장의 '기억'으로 정리하라.
설명 없이 기억 문장만 출력하라.

[대화]
{dialog}
"""


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[\s,.?!~\"'()\[\]{}:;]+", text) if len(t) >= 2}


def search_memories(session_id: str, query: str, k: int = TOP_K) -> list[str]:
    """현재 발화와 관련度高은 과거 기억을 검색한다."""
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []
    with _conn() as conn:
        rows = conn.execute(
            "SELECT text FROM memories WHERE session_id = ? ORDER BY id DESC LIMIT 200",
            (session_id,),
        ).fetchall()
    scored: list[tuple[float, str]] = []
    for (text,) in rows:
        overlap = len(q_tokens & _tokenize(text))
        if overlap > 0:
            scored.append((overlap, text))
    scored.sort(key=lambda t: -t[0])
    return [text for _, text in scored[:k]]


def save_memory(session_id: str, turn: int, text: str) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT INTO memories (session_id, turn, text, created_at) VALUES (?, ?, ?, ?)",
            (session_id, turn, text.strip(), time.time()),
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
    with _conn() as conn:
        if session_id:
            row = conn.execute("SELECT COUNT(*) FROM memories WHERE session_id=?", (session_id,)).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM memories").fetchone()
    return row[0]


# ── 대화 히스토리 영속화 ──

def load_history(session_id: str) -> list[dict]:
    with _conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS histories (session_id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at REAL NOT NULL)"
        )
        row = conn.execute("SELECT data FROM histories WHERE session_id=?", (session_id,)).fetchone()
    return json.loads(row[0]) if row else []


def save_history(session_id: str, history: list[dict]) -> None:
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
    with _conn() as conn:
        conn.execute("DELETE FROM memories WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM histories WHERE session_id=?", (session_id,))
