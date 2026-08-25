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


@pytest.fixture(autouse=True)
def isolate_characters_dir(monkeypatch, tmp_path):
    """테스트에서 생성한 캐릭터 카드가 실제 characters/ 디렉토리를 오염시키지 않도록 격리.
    기존 시드 카드는 임시 디렉토리로 복사해 목록 조회 테스트가 계속 동작하도록 한다."""
    import shutil
    from library.creators import builder

    real_dir = builder.CHARACTERS_DIR
    fake_dir = tmp_path / "characters"
    if real_dir.exists():
        shutil.copytree(real_dir, fake_dir)
        # 실제 유저 제작 카드까지 복사되지 않도록 루트의 테스트 산출물은 제외
        for f in fake_dir.glob("char_custom_*.json"):
            f.unlink()
    monkeypatch.setattr(builder, "CHARACTERS_DIR", fake_dir)


@pytest.fixture()
def tmp_memory_db(monkeypatch, tmp_path):
    """memory store를 임시 DB로 격리."""
    from library.memory import store

    db = tmp_path / "test_memory.db"
    monkeypatch.setattr(store, "DB_PATH", db)
    return store
