# SQLD AI Trainer — 작업 총정리 (1~5)

> 최종 업데이트: 2026-06-06

SQLite → Railway Postgres(pgvector) 마이그레이션 및 문제 임베딩 파이프라인 구축 작업의 전체 요약.
단계별 상세는 하단 [관련 상세 문서](#관련-상세-문서) 참조.

---

## 1. 인프라: SQLite → Railway Postgres 마이그레이션

| 항목 | 내용 |
|------|------|
| 클라우드 DB | Railway Postgres (PG 18.4) + pgvector 0.8.2 |
| 연결 | `DATABASE_URL` 환경변수 우선 → 없으면 로컬 SQLite 폴백 |
| 드라이버 | `psycopg2-binary` 추가 (`postgres://` → `postgresql://` 자동 보정) |
| 안정화 | TCP keepalive `connect_args` + `pool_pre_ping` (Railway 프록시 끊김 방지) |
| 3대 수정 | ① 드라이버 누락 ② seeding을 빌드→런타임(lifespan) 이동 ③ `/health` 빈 테이블 게이트 |

## 2. 스키마 설계

- **provenance 5컬럼** (`questions` 테이블): `source`(original/generated) · `status`(active/pending/rejected) · `generated_from` · `fitness_score` · `created_at`
  → 생성문제/기존문제 구분 + 재활용 플라이휠 대비
- **`question_embeddings` 테이블** (pgvector): `vector(1536)` + FK CASCADE + HNSW cosine 인덱스
- **방어적 설계**: `HAS_PGVECTOR` 가드 · `ensure_vector_extension()` · pgvector 없으면 코어 테이블만 생성(크래시 방지)

## 3. 데이터 적재

| 스크립트 | 결과 |
|----------|------|
| `load_questions.py` (신규) | JSON → `questions` 297건 적재. 멱등 청크 ON CONFLICT upsert |
| `vectorize_questions.py` (신규) | Gemini `gemini-embedding-001` 1536d, L2 정규화, `RETRIEVAL_DOCUMENT` → 297건 임베딩 적재 + HNSW 생성 |

## 4. 실행 / 환경 구성

- `run.py` (신규): `.env`의 `HOST`/`PORT`/`RELOAD` 기반 uvicorn 기동 (로컬 개발용)
- `.env` ↔ `.env.example` 정리 — `DATABASE_URL`만 `.env`로 분리 (`EMBED_DIM`/모델명은 스키마 상수라 코드에 유지)
- `requirements_api.txt` 에 `psycopg2-binary` · `pgvector` · `google-genai` 추가

## 5. 검증 (Railway DB health check)

```
PostgreSQL 18.4 · pgvector 0.8.2
questions 297 / question_embeddings 297 (100% 커버리지)
embedding dim 1536 · source=original×297 · status=active×297
HNSW 인덱스 ix_qemb_hnsw (vector_cosine_ops) ✅
```

---
