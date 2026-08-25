import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def force_mock_inference(monkeypatch):
    """모든 테스트에서 LLM/임베딩 호출을 차단해 빠르고 결정적으로 유지."""
    from library.inference import gemma_client

    monkeypatch.setitem(gemma_client._CONFIG["model"], "endpoint", "mock")
    # 임베딩은 네트워크 호출이므로 항상 None (store가 오버랩 폴백 사용)
    monkeypatch.setattr(gemma_client, "embed", lambda text: None)


@pytest.fixture()
def tmp_memory_db(monkeypatch, tmp_path):
    """memory store를 임시 DB로 격리."""
    from library.memory import store

    db = tmp_path / "test_memory.db"
    monkeypatch.setattr(store, "DB_PATH", db)
    return store
