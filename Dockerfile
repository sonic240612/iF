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

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn library.api:app --host 0.0.0.0 --port ${PORT}"]
