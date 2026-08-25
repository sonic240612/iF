# ── 1단계: 프론트엔드 빌드 ──
FROM node:20-alpine AS web-build
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ── 2단계: 백엔드 + 정적 SPA 서빙 ──
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY library/ library/
COPY configs/ configs/
COPY characters/ characters/
COPY --from=web-build /build/dist web/dist/

# Hugging Face Spaces: non-root 유저(1000) 실행 필수 + 쓰기 가능한 데이터 디렉토리
RUN mkdir -p /app/data && chown -R 1000:1000 /app
USER 1000

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn library.api:app --host 0.0.0.0 --port ${PORT}"]
