"""
Phase 5 — SQLD Adaptive Learning Platform FastAPI Backend

실행:
    uvicorn api.main:app --reload --port 8000

Swagger UI:
    http://localhost:8000/docs

환경 변수:
    DATABASE_URL     Postgres(pgvector) 연결 URL (없으면 로컬 SQLite 폴백)
    JWT_SECRET_KEY   JWT 서명 키 (미설정 시 기동 실패)
    OLLAMA_API_KEY   RAG 해설 LLM(Ollama Cloud) 키 (없으면 원본 해설 fallback)
    GEMINI_API_KEY   문제 임베딩(gemini-embedding-001) 생성용 (적재/벡터화 시)
"""
import asyncio
import logging
import os
import pathlib
import sys
from contextlib import asynccontextmanager

from dotenv import load_dotenv

logger = logging.getLogger("uvicorn.error")

# 저장소 루트 .env 로드 (JWT/OLLAMA/GEMINI/CORS/DATABASE_URL). 컨테이너엔 .env 없음 → no-op.
load_dotenv(pathlib.Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.database import create_tables
from api.routers import auth, explain, logs, predict, progress, questions, recommend
from api.state import app_state

def _log_mem(label: str) -> None:
    try:
        import resource
        kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        print(f"[MEM] {label}: {kb // 1024} MB", flush=True)
    except Exception:
        pass


def _seed_questions_if_empty() -> None:
    """questions 테이블이 비어 있으면 JSON 으로부터 1회 적재 (idempotent).

    Railway/Postgres 는 이미지 빌드 시점에 DB 에 접근할 수 없으므로,
    seeding 은 빌드가 아니라 런타임(앱 시작)에 수행한다. merge 기반이라 재시작마다 안전.
    """
    from api.database import Question, SessionLocal

    try:
        with SessionLocal() as db:
            count = db.query(Question).count()
    except Exception as e:
        print(f"[seed] questions 카운트 실패(테이블 미생성 가능): {e}", flush=True)
        count = 0

    if count > 0:
        print(f"[seed] questions 이미 {count}건 → seeding 생략", flush=True)
        return

    print("[seed] questions 비어 있음 → load_questions 적재 시작", flush=True)
    try:
        from load_questions import build_dataframe, load
        n = load(build_dataframe())
        print(f"[seed] questions {n}건 적재 완료", flush=True)
    except Exception as e:
        print(f"[seed] 적재 실패(서버는 계속 실행, /health 가 미준비로 보고): {e}", flush=True)


def _bootstrap() -> None:
    """startup 동기 작업: questions seeding(빈 경우) → 앱 상태 로드. 실행기 스레드에서 호출."""
    _seed_questions_if_empty()
    app_state.load()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_mem("startup-begin")
    create_tables()
    app.state.models = app_state
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _bootstrap)
    except Exception as e:
        print(f"[FATAL] 데이터 로딩 실패: {e}", file=sys.stderr, flush=True)
        raise
    _log_mem("startup-complete")
    yield


app = FastAPI(
    title="SQLD 적응형 학습 플랫폼 API",
    description=(
        "Phase 5 — FastAPI 서비스\n\n"
        "## 인증 방식\n"
        "- **게스트**: `POST /auth/guest` → Bearer 토큰 발급 → 문제 조회·해설 조회 가능\n"
        "- **회원**: `POST /auth/register` 또는 `POST /auth/login` → Bearer 토큰 발급 → 전체 기능 사용\n\n"
        "## 주요 기능\n"
        "- 문제 조회 (공개)\n"
        "- RAG AI 해설 생성 (공개)\n"
        "- 풀이 결과 저장 (인증 필요)\n"
        "- DKT ZPD 개인화 추천 (인증 필요)\n"
        "- 학습 진도 대시보드 (인증 필요)\n"
        "- 오답 확률 예측 (인증 필요)\n"
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — 로컬 개발 서버 + Vercel 프로덕션/프리뷰 + 환경변수로 추가 오리진 허용
_extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://sqld-ai-trainer.vercel.app",
        *_extra_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(explain.router)
app.include_router(logs.router)
app.include_router(recommend.router)
app.include_router(progress.router)
app.include_router(predict.router)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "SQLD Adaptive Learning API", "version": "1.0.0"}


@app.get("/health", tags=["health"])
def health():
    state = app.state.models if hasattr(app.state, "models") else None
    # 빈 DataFrame(테이블은 있으나 0건)도 미준비로 본다 → seeding 실패를 헬스체크로 노출
    data_ready = (
        state is not None
        and state.questions_df is not None
        and len(state.questions_df) > 0
    )
    body = {
        "status": "ok" if data_ready else "initializing",
        "data_ready": data_ready,
        "models": {
            "recommender": state.recommender is not None if state else False,
            "dkt": state.dkt_model is not None if state else False,
            "explainer": state.explainer is not None if state else False,
            "predictor": state.predictor_model is not None if state else False,
        },
    }
    if not data_ready:
        logger.warning("[Health] questions_df 미준비 → 503 반환")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=body)
    logger.info("[Health] 정상 → 200 반환")
    return body
