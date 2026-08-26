"""LLM 추론 인터페이스 — Gemma 4 26B A4B (Gemini API, OpenAI 호환 엔드포인트).

configs/base.toml 의 [model].endpoint 에 따라 분기:
  - "mock": 개발용 규칙 기반 응답
  - "gemma": 실추론 (Google Gemini API OpenAI 호환 모드)

API 키 관리:
  - 키는 .env 의 IF_API_KEYS (쉼표 구분). CLI로 추가/제거 가능:
      python -m library.inference.key_cli list / add / remove (키 추가 시 .env에 GOOGLE_API_KEY_N으로 자동 저장)
  - 하나의 키가 429(레이트리밋)면 해당 키는 2분간 쿨다운되어 제외됨.
  - 그 외 5xx, 타임아웃, 무효 키(400) 등은 즉시 다음 키로 재시도.
"""
from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.request
from pathlib import Path

import tomllib

from library.inference.key_manager import pool, get_keys

ROOT = Path(__file__).resolve().parents[2]
with open(ROOT / "configs" / "base.toml", "rb") as f:
    _CONFIG = tomllib.load(f)

ENV_PATH = ROOT / ".env"


def _load_env_file() -> None:
    """간단한 .env 로더 (키=값 형식). 이미 설정된 환경변수는 덮어쓰지 않음."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def get_api_keys() -> list[str]:
    """IF_API_KEYS 환경변수(쉼표 구분)에서 키 목록 로드."""
    _load_env_file()
    raw = os.environ.get("IF_API_KEYS", "")
    return [k.strip() for k in raw.split(",") if k.strip()]



# ── 사용 가능한 모델 ──
AVAILABLE_MODELS = {
    "gemma4": {
        "id": "gemma-4-26b-a4b-it",
        "label": "Gemma 4",
    },
    "gemini_35_flash_lite": {
        "id": "gemini-3.5-flash-lite",
        "label": "Gemini 3.5 Flash Lite",
    },
}
DEFAULT_MODEL_KEY = "gemma4"


def get_available_models() -> list[dict]:
    """프론트엔드용 모델 목록."""
    return [{"key": k, **v} for k, v in AVAILABLE_MODELS.items()]


def resolve_model_id(model_key: str | None) -> str:
    """모델 키 → 실제 모델 ID. 미등록/빈값이면 기본값 반환."""
    if model_key and model_key in AVAILABLE_MODELS:
        return AVAILABLE_MODELS[model_key]["id"]
    return _CONFIG["model"].get("model", "gemma-4-26b-a4b-it")


# 이 에러 코드들이 나오면 다음 키로 폴백 (429는 별도: KeyPool 쿨다운 적용)
RETRYABLE_STATUS = {408, 500, 502, 503, 504}


MOCK_REPLIES = {
    "cold": ["…또 왔네. 할 말이면 빨리 해.", "관심 없어. 돌아가.", "그래서? 내가 뭘 하라고?"],
    "tsundere": ["따、따라온 거 아냐! 그냥 우연히 마주친 것뿐이야.", "바보… 밥은 먹었어?", "흥, 언제까지 그렇게 있을 건데. …안 궁금하거든!"],
    "warm": ["오늘 하루도 고생 많았어. 이리 와서 쉬어.", "네 목소리 들으니까 마음이 편안해져.", "무슨 일 있으면 언제든 말해줘, 알았지?"],
    "affectionate": ["사랑해, 오늘도. 내일도. 계속.", "너만 보면 심장이 막 뛰어. 책임져~", "우리 영원히 함께하기로 했잖아?"],
    "obsessive": ["방금… 나 말고 누구랑 얘기했어? 솔직하게 말해줘.", "네가 어디 있는지 다 알아. 안심해, 내가 항상 지켜볼게.", "나만 바라봐 줘… 부탁이야."],
    "hostile": ["이제 그만해. 더는 듣고 싶지 않아.", "…당신 같은 사람, 처음부터 만날 걸 그랬네."],
}
DEFAULT_REPLIES = ["응, 계속할게. 네 얘기 듣고 싶어.", "흠… 그렇게 생각하네. 너는 어려?", "재미있네. 이어서 얘기해 줘."]


class AllKeysFailedError(RuntimeError):
    pass


class ContextOverflowError(RuntimeError):
    """프롬프트가 모델의 최대 입력 토큰 수를 초과했을 때."""


_THOUGHT_RE = re.compile(r"<thought>.*?</thought>", re.DOTALL)

# 마지막 생성의 finish_reason (api.py가 잘림 여부 확인용)
_finish_reason = {"value": None}


def was_truncated() -> bool:
    return _finish_reason["value"] == "length"


def reset_finish_state() -> None:
    _finish_reason["value"] = None


def strip_thought(text: str) -> str:
    """Gemma 4의 <thought>…</thought> 추론 블록 제거."""
    cleaned = _THOUGHT_RE.sub("", text)
    return cleaned.strip()


def _call_endpoint(base_url: str, model: str, api_key: str, payload: dict) -> str:
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.load(resp)
    content = strip_thought(data["choices"][0]["message"]["content"])
    if data["choices"][0].get("finish_reason") == "length":
        print("[gemma_client] warning: 응답이 max_tokens로 잘렸습니다 (finish_reason=length)")
        _finish_reason["value"] = "length"
    else:
        _finish_reason["value"] = data["choices"][0].get("finish_reason")
    if not content:
        # 빈 응답도 재시도 가능한 장애로 간주
        raise urllib.error.HTTPError(req.full_url, 500, "empty response", hdrs=None, fp=None)
    return content


def generate_remote(prompt: str) -> str:
    """키 로테이션 폴백이 적용된 Gemma 추론.

    - KeyPool이 쿨다운 중이 아닌 키를 공급. 429 발생 시 해당 키는 2분간 쿨다운.
    - 5xx/네트워크 오류/무효 키(400)는 즉시 다음 사용 가능한 키로 재시도.
    """
    if not get_keys():
        raise RuntimeError("사용 가능한 API 키가 없습니다 (.env의 IF_API_KEYS 확인)")

    base_url = _CONFIG["model"].get(
        "base_url", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    model = _CONFIG["model"].get("model", "gemma-4-26b-a4b-it")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": _CONFIG["model"].get("max_tokens", 1024),
        "temperature": _CONFIG["model"].get("temperature", 0.9),
    }

    last_err: Exception | None = None
    max_attempts = max(len(get_keys()) * 2, 4)  # 무한루프 방지 상한
    for _ in range(max_attempts):
        key = pool.next_key()
        try:
            return _call_endpoint(base_url, model, key, payload)
        except urllib.error.HTTPError as e:
            last_err = e
            body = ""
            try:
                body = e.read().decode(errors="ignore")
            except Exception:
                pass
            # 400이라도 "invalid API key" 류면 무효 키 → 다음 키로 폴백
            invalid_key = e.code == 400 and any(
                s in body.lower() for s in ("api key", "api_key", "unregistered", "permission")
            )
            token_overflow = e.code in (400, 413) and any(
                s in body.lower() for s in ("maximum number of tokens", "token limit",
                                            "input tokens", "context length")
            )
            if token_overflow:
                raise ContextOverflowError("프롬프트 길이가 모델의 최대 입력 토큰 수를 초과했습니다.")
            if e.code == 429:
                # 레이트리밋: 이 키는 2분간 쿨다운 후 다른 키로 계속
                pool.mark_rate_limited(key)
                print(f"[gemma_client] key ...{key[-6:]} rate-limited (429) → 2분 쿨다운, next key")
                continue
            if e.code in RETRYABLE_STATUS or invalid_key:
                print(f"[gemma_client] key ...{key[-6:]} failed ({e.code}), trying next key")
                continue
            raise  # 그 외 클라이언트 오류는 프롬프트 문제일 수 있으므로 즉시 상위로
        except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError) as e:
            last_err = e
            print(f"[gemma_client] key ...{key[-6:]} network/parse error: {e}, trying next key")
            continue

    raise AllKeysFailedError(f"모든 API 키 실패: {last_err}")


def generate_remote_stream(prompt: str, model_key: str | None = None):
    """SSE 토큰 스트리밍 (OpenAI 호환 stream=true).

    첫 청크 수신 전 오류 시 다음 키로 폴백.
    model_key가 지정되면 해당 모델로 요청 (기본값: 설정 파일의 모델).
    """
    if not get_keys():
        raise RuntimeError("사용 가능한 API 키가 없습니다")
    base_url = _CONFIG["model"].get(
        "base_url", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    model = resolve_model_id(model_key) if model_key else _CONFIG["model"].get("model", "gemma-4-26b-a4b-it")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": _CONFIG["model"].get("max_tokens", 1024),
        "temperature": _CONFIG["model"].get("temperature", 0.9),
        "stream": True,
    }
    last_err = None
    for _ in range(max(len(get_keys()), 2)):
        key = pool.next_key()
        try:
            req = urllib.request.Request(
                base_url.rstrip("/") + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                for raw_line in resp:
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:"):].strip()
                    if data_str == "[DONE]":
                        return
                    try:
                        chunk = json.loads(data_str)
                        choice = chunk["choices"][0]
                        fr = choice.get("finish_reason")
                        if fr:
                            _finish_reason["value"] = fr
                            if fr == "length":
                                print("[gemma_client] warning: 스트림 응답 잘림 (finish_reason=length)")
                        delta = choice["delta"].get("content")
                        if delta:
                            yield strip_thought_delta(delta)
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue
            return
        except urllib.error.HTTPError as e:
            last_err = e
            body = ""
            try:
                body = e.read().decode(errors="ignore")
            except Exception:
                pass
            invalid_key = e.code == 400 and any(
                s in body.lower() for s in ("api key", "api_key", "unregistered", "permission")
            )
            token_overflow = e.code in (400, 413) and any(
                s in body.lower() for s in ("maximum number of tokens", "token limit",
                                            "input tokens", "context length")
            )
            if token_overflow:
                raise ContextOverflowError("프롬프트 길이가 모델의 최대 입력 토큰 수를 초과했습니다.")
            if e.code == 429:
                pool.mark_rate_limited(key)
                print(f"[gemma_client] stream: key ...{key[-6:]} 429 → cooldown, next")
                continue
            if e.code in RETRYABLE_STATUS or invalid_key:
                continue
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = e
            print(f"[gemma_client] stream network error: {e}, next key")
            continue
    raise AllKeysFailedError(f"모든 API 키 실패(스트림): {last_err}")


def strip_thought_delta(delta: str) -> str:
    """<thought> 블록 내부 토큰은 흘려보내지 않는다.
    단순화를 위해 thought 태그 등장 이후는 상위에서 버퍼링 없이 처리하기 어려우므로,
    여기서는 태그 완결성 검사만 하고 상위 API 레이어가 최종 텍스트에서 정리한다.
    실시간 출력 품질을 위해 thought 시작이 감지되면 빈 문자열을 반환한다."""
    # 개별 델타에는 태그가 쪼개져 올 수 있으므로, 전역 버퍼 플래그로 관리
    global _IN_THOUGHT
    if "<thought>" in delta:
        _IN_THOUGHT = True
    if _IN_THOUGHT:
        if "</thought>" in delta:
            _IN_THOUGHT = False
            delta = delta.split("</thought>", 1)[1]
        else:
            return ""
    return delta

_IN_THOUGHT = False


def reset_thought_state() -> None:
    global _IN_THOUGHT
    _IN_THOUGHT = False


# ── 임베딩 (RAG 벡터 검색용) ──

EMBED_MODEL = "text-embedding-004"


def embed(text: str) -> list[float] | None:
    """텍스트 임베딩 벡터 반환. 실패 시 None (호출부가 토큰 오버랩 폴백 사용)."""
    if not text.strip() or not get_keys():
        return None
    base_url = _CONFIG["model"].get(
        "base_url", "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    payload = {"model": EMBED_MODEL, "input": text}
    for _ in range(max(len(get_keys()), 2)):
        key = pool.next_key()
        try:
            req = urllib.request.Request(
                base_url.rstrip("/") + "/embeddings",
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
            return data["data"][0]["embedding"]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                pool.mark_rate_limited(key)
            continue
        except Exception:
            continue
    return None


def generate(prompt: str, mood: str = "neutral", max_tokens: int = 1024) -> str:
    endpoint = _CONFIG["model"].get("endpoint", "mock")
    if endpoint == "gemma":
        return generate_remote(prompt)
    pool = MOCK_REPLIES.get(mood, DEFAULT_REPLIES)
    return random.choice(pool)
