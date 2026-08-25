"""API 키 관리 — GOOGLE_API_KEY* 자동 수집 + Round Robin + 429 쿨다운.

.env 파일 형식:
    GOOGLE_API_KEY=AQ.xxxx
    GOOGLE_API_KEY_2=AQ.yyyy
    GOOGLE_API_KEY_3=AQ.zzzz
    ... (_2, _3, _4 ... 번호는 몇이든 가능)

- GOOGLE_API_KEY 로 시작하는 환경변수를 전부 수집하여 키 풀로 사용.
- 요청마다 Round Robin 방식으로 키를 순회하며 사용.
- 429 레이트리밋 발생 시 해당 키는 COOLDOWN_SECONDS(2분)간 제외되며,
  쿨다운이 끝나면 자동으로 로테이션에 복귀.

CLI 사용법:
    python -m library.inference.key_cli list            # 키 목록 조회
    python -m library.inference.key_cli add KEY [...]   # 키 추가 (자동 다음 번호 부여)
    python -m library.inference.key_cli remove KEY      # 키 제거 (접두사 매칭 가능)
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"
KEY_PREFIX = "GOOGLE_API_KEY"

COOLDOWN_SECONDS = 120  # 429 발생 시 키당 쿨다운 2분


def load_env_file() -> None:
    """간단한 .env 로더. 이미 프로세스에 설정된 환경변수는 우선 유지."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_keys() -> list[str]:
    """GOOGLE_API_KEY* 환경변수를 모두 수집해 안정적 순서(번호순)로 반환."""
    load_env_file()
    pat = re.compile(rf"^{KEY_PREFIX}(_\d+)?$")
    found: list[tuple[int, str]] = []
    for name, val in os.environ.items():
        m = pat.match(name)
        if m and val.strip():
            idx = int(m.group(1)[1:]) if m.group(1) else 0
            found.append((idx, val.strip()))
    found.sort(key=lambda t: t[0])
    return [v for _, v in found]


def save_keys(keys: list[str]) -> None:
    """키 목록을 .env에 GOOGLE_API_KEY[_N] 형식으로 저장 (기존 다른 변수는 유지)."""
    lines: list[str] = []
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith(KEY_PREFIX):
                continue
            lines.append(line)
    for i, key in enumerate(keys):
        name = KEY_PREFIX if i == 0 else f"{KEY_PREFIX}_{i + 1}"
        lines.append(f"{name}={key}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    # 현재 프로세스에도 반영
    for name in list(os.environ):
        if name.startswith(KEY_PREFIX):
            del os.environ[name]
    for i, key in enumerate(keys):
        name = KEY_PREFIX if i == 0 else f"{KEY_PREFIX}_{i + 1}"
        os.environ[name] = key


def add_keys(*new_keys: str) -> list[str]:
    keys = get_keys()
    for nk in new_keys:
        nk = nk.strip()
        if nk and nk not in keys:
            keys.append(nk)
    save_keys(keys)
    return keys


def remove_key(target: str) -> list[str]:
    keys = [k for k in get_keys() if not k.startswith(target)]
    save_keys(keys)
    return keys


class KeyPool:
    """Round Robin 키 공급자 + 429 쿨다운 추적."""

    def __init__(self, cooldown_seconds: int = COOLDOWN_SECONDS) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._cooldown_until: dict[str, float] = {}
        self._rr_index = 0

    def mark_rate_limited(self, key: str) -> None:
        """429 발생 → 이 키는 2분간 로테이션에서 제외."""
        self._cooldown_until[key] = time.time() + self.cooldown_seconds

    def next_key(self) -> str:
        """Round Robin으로 다음 사용 가능한 키 반환.

        쿨다운 중인 키는 건너뛰고, 모든 키가 쿨다운 중이면
        가장 먼저 해제되는 키까지 대기 후 재시도한다.
        """
        keys = get_keys()
        if not keys:
            raise RuntimeError(
                "사용 가능한 API 키가 없습니다. .env에 GOOGLE_API_KEY=... 를 추가하세요."
            )
        now = time.time()
        avail = [k for k in keys if self._cooldown_until.get(k, 0) <= now]
        if not avail:
            earliest = min(self._cooldown_until.values())
            wait = max(0.5, min(earliest - now, 30))
            print(f"[KeyPool] 모든 키 쿨다운 중 — {wait:.1f}초 대기 후 재시도")
            time.sleep(wait)
            avail = [k for k in keys if self._cooldown_until.get(k, 0) <= time.time()]
            if not avail:
                raise RuntimeError("모든 API 키가 쿨다운 상태입니다.")

        # Round Robin: 이전 위치부터 순회하며 첫 사용 가능 키 선택
        start = self._rr_index % len(avail)
        key = avail[start]
        self._rr_index = (start + 1) % len(avail)
        return key

    def status(self) -> list[dict]:
        now = time.time()
        return [
            {
                "index": i,
                "key_tail": f"...{k[-6:]}",
                "available": self._cooldown_until.get(k, 0) <= now,
                "cooldown_remaining_s": round(max(0, self._cooldown_until.get(k, 0) - now), 1),
            }
            for i, k in enumerate(get_keys(), 1)
        ]


pool = KeyPool()
