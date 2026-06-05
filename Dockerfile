FROM python:3.11-slim

# stdout 버퍼링 비활성화 — 크래시 전 로그 손실 방지 및 await 동작 확인
ENV PYTHONUNBUFFERED=1

# FAISS가 필요로 하는 OpenMP 런타임
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 의존성 먼저 설치 (소스 변경 시 캐시 재사용)
COPY backend/requirements_api.txt .
RUN pip install --no-cache-dir -r requirements_api.txt

# 소스 코드 + 모델 아티팩트 복사
COPY backend/ ./backend/

# outputs/는 state.py가 backend/outputs/ 로 참조하므로 해당 위치에 복사
COPY outputs/ ./backend/outputs/

# datasets/json/은 state.py가 3레벨 상위(=/app)에서 참조
COPY datasets/json/ ./datasets/json/

# uvicorn을 backend/ 내부에서 실행해야 api.* 임포트가 동작
WORKDIR /app/backend

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
