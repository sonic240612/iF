"""Hugging Face Spaces (Gradio SDK) 진입점.

HF의 Gradio Space는 저장소의 app.py를 실행하고 7860 포트를 기대한다.
Gradio UI 대신 우리 FastAPI 앱을 직접 uvicorn으로 띄운다.
"""
import os

import uvicorn

from library.api import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"[hf] starting iF API on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
