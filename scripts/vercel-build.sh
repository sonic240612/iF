#!/usr/bin/env bash
# Vercel 배포용 빌드 스크립트 (buildCommand 256자 제한 우회)
set -e

echo "[1/4] Python 의존성 설치"
pip install -q -r requirements.txt

echo "[2/4] 프론트엔드 의존성 설치"
cd web
npm ci --no-audit --no-fund
# esbuild postinstall이 차단된 환경 대비 폴백
node node_modules/esbuild/install.js || npm rebuild esbuild || echo "[warn] esbuild install.js 스킵 (optional deps로 커버됨)"

echo "[3/4] SPA 빌드"
npm run build

echo "[4/4] 백엔드 런타임 번들링"
cd ..
mkdir -p api/runtime
cp -r library api/runtime/
cp -r configs api/runtime/
cp -r characters api/runtime/

echo "[done] 빌드 완료"
