"""Vercel Python 함수 진입점.

Vercel은 api/index.py의 `app` 객체를 ASGI 앱으로 실행한다.
빌드 시 런타임 모듈들이 api/runtime/으로 복사되므로 경로를 추가한다.
"""
import sys
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parent / "runtime"
if RUNTIME_DIR.exists():
    sys.path.insert(0, str(RUNTIME_DIR))

from library.api import app  # noqa: E402
