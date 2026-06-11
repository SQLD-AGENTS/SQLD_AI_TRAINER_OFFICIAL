"""
questions 임베딩을 Google Gemini(gemini-embedding-001)로 생성해 question_embeddings(pgvector)에 적재.

- 차원: 1536 (output_dimensionality; 3072 동급 품질 + pgvector HNSW 인덱스(≤2000) 가능)
- gemini-embedding-001 은 3072 외 차원에서 L2 정규화가 필요 → 수동 정규화
- task_type 은 단일 원천 EMBED_TASK_TYPE(SEMANTIC_SIMILARITY) 참조; model_name 은 파생 EMBED_MODEL_NAME(:ss)
- 멱등: 아직 임베딩 안 된 문제만 처리. Postgres + pgvector 전용.

환경변수:
    GEMINI_API_KEY   (필수)  Google AI Studio 키
    DATABASE_URL     (필수)  Railway Postgres (pgvector 템플릿)

실행 (backend/ 에서):
    $env:GEMINI_API_KEY = "..."
    $env:DATABASE_URL   = "postgresql://...proxy.rlwy.net:.../railway"
    python vectorize_questions.py
"""
import json
import math
import os
import pathlib
import sys
import time

# Windows 콘솔(cp949) 비-cp949 문자 print 크래시 방지 — UTF-8(errors='replace') 고정.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

# 저장소 루트 .env 로드 → GEMINI_API_KEY 등. (DATABASE_URL 은 셸 환경 우선: override=False)
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

# doc_builder(SSOT) 임포트 경로 — load_questions 와 동일 패턴
_SRC_DATA = pathlib.Path(__file__).resolve().parent / "src" / "data"
if str(_SRC_DATA) not in sys.path:
    sys.path.insert(0, str(_SRC_DATA))

import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

import doc_builder  # noqa: E402  — 임베딩 입력의 단일 원천
from api.database import (  # noqa: E402
    EMBED_DIM,
    EMBED_MODEL_NAME,
    EMBED_TASK_TYPE,
    HAS_PGVECTOR,
    QuestionEmbedding,
    _is_sqlite,
    create_tables,
    engine,
)

# 무료 티어의 binding 제약은 RPM(100)이 아니라 TPM(~30,000). doc 1건이 최대 3000자(~750토큰)라
# 배치 100이면 ~75,000토큰/호출 → SQL-heavy 문항 구간에서 TPM 초과로 429가 지속된다.
# 30 × ~750 ≈ 22,500토큰/호출 < 30,000 TPM 으로 마진 확보(분당 1배치 throttle).
BATCH = 30  # Gemini embed_content 배치 크기 (TPM 제약 기준)
NORM_TOL = 1e-6  # L2 노름 카나리 허용 오차


def _json_col(v):
    """assets/choices 컬럼 정규화 — Postgres JSONB(객체) / SQLite JSON(문자열) 양쪽 대응."""
    if v is None:
        return None
    if isinstance(v, float):  # NaN
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v  # 이미 list/dict


def _doc_text(row) -> str:
    """임베딩 대상 = SSOT doc_builder.build_doc(assets, choices, explanation).

    파생 question_text 가 아니라 DB 원본 컬럼에서 직접 재구성 — 입력의 단일 원천 원칙.
    json_parser 가 content_hash 산출에 쓴 것과 '같은 함수'라 해시-임베딩 입력이 일치한다.
    """
    return doc_builder.build_doc(
        _json_col(row.get("assets")),
        _json_col(row.get("choices")),
        row.get("explanation") or "",
    )


def _fetch_unembedded() -> pd.DataFrame:
    """스테일(신규·내용변경·모델교체) 문제만 반환 — 3조건 스테일 쿼리."""
    sql = text(
        """
        SELECT q.question_id, q.assets, q.choices, q.explanation, q.content_hash
        FROM questions q
        LEFT JOIN question_embeddings e ON e.question_id = q.question_id
        WHERE e.question_id IS NULL
           OR e.content_hash <> q.content_hash
           OR e.model_name  <> :model
        ORDER BY q.question_id
        """
    )
    return pd.read_sql_query(sql, engine, params={"model": EMBED_MODEL_NAME})


def _embed_batch(client, texts: list) -> list:
    """Gemini 임베딩 호출 → L2 정규화된 (len(texts), EMBED_DIM) 리스트. (공용 헬퍼 위임)"""
    from api.embeddings import embed_texts

    return embed_texts(texts, task_type=EMBED_TASK_TYPE, client=client)


def _embed_with_retry(client, texts: list, max_retries: int = 8) -> list:
    """무료 티어 429(RESOURCE_EXHAUSTED) 시 60초 대기 후 재시도."""
    from google.genai.errors import ClientError

    for attempt in range(max_retries):
        try:
            return _embed_batch(client, texts)
        except ClientError as e:
            if getattr(e, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(e):
                print(
                    f"  [rate-limit] 429 → 60초 대기 후 재시도 ({attempt + 1}/{max_retries})",
                    flush=True,
                )
                time.sleep(60)
                continue
            raise
    raise RuntimeError("Gemini 429 재시도 한도 초과 — 잠시 후 다시 실행하세요(멱등, 이어서 진행됨).")


def _upsert(rows: list) -> int:
    """청크 ON CONFLICT upsert (프록시 왕복 최소화)."""
    processed = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            stmt = pg_insert(QuestionEmbedding.__table__).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["question_id"],
                set_={
                    "embedding": stmt.excluded.embedding,
                    "model_name": stmt.excluded.model_name,
                    # 스테일 키: 임베딩 시점 questions.content_hash 기록 (멱등·V1 불변식)
                    "content_hash": stmt.excluded.content_hash,
                },
            )
            conn.execute(stmt)
            processed += len(batch)
    return processed


def ensure_hnsw_index() -> None:
    """HNSW(cosine) 인덱스 생성(존재 시 무시). 정규화된 벡터라 cosine 사용."""
    with engine.connect() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_qemb_hnsw "
                "ON question_embeddings USING hnsw (embedding vector_cosine_ops)"
            )
        )
        conn.commit()
    print("[vectorize] HNSW 인덱스 확인 완료")


def main() -> None:
    if _is_sqlite or not HAS_PGVECTOR or QuestionEmbedding is None:
        raise SystemExit(
            "vectorize_questions 는 Postgres + pgvector 에서만 동작합니다.\n"
            "DATABASE_URL 이 Railway Postgres(pgvector 템플릿)를 가리키는지 확인하세요."
        )
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY 환경변수를 설정하세요 (Google AI Studio 키).")

    from google import genai

    client = genai.Client(api_key=api_key)

    create_tables()  # question_embeddings(+확장) 보장

    df = _fetch_unembedded()
    if df.empty:
        print("[vectorize] 임베딩할 신규 문제 없음 (이미 최신).")
        ensure_hnsw_index()
        return

    qids = df["question_id"].tolist()
    hashes = df["content_hash"].tolist()
    texts = [_doc_text(r) for _, r in df.iterrows()]
    print(
        f"[vectorize] 대상 {len(texts)}건 → Gemini({EMBED_MODEL_NAME}, dim={EMBED_DIM}) 임베딩 시작 "
        f"(무료 티어 100건/분 → 배치마다 throttle)..."
    )

    done, skipped = 0, 0
    for i in range(0, len(texts), BATCH):
        vecs = _embed_with_retry(client, texts[i : i + BATCH])
        rows = []
        for qid, h, v in zip(qids[i : i + BATCH], hashes[i : i + BATCH], vecs):
            assert len(v) == EMBED_DIM, f"차원 불일치: {len(v)} != {EMBED_DIM}"
            # L2 노름 카나리 — 비정규 벡터는 skip(ck_qsim_similarity 1차 방어선)
            norm = math.sqrt(sum(x * x for x in v))
            if abs(norm - 1.0) >= NORM_TOL:
                print(f"  [warn] L2 노름 이탈 qid={qid} norm={norm:.6f} → skip", flush=True)
                skipped += 1
                continue
            rows.append(
                {
                    "question_id": str(qid),
                    "embedding": v,
                    "model_name": EMBED_MODEL_NAME,
                    "content_hash": h,
                }
            )
        if rows:
            _upsert(rows)  # 배치 단위 저장 → 중단돼도 재실행 시 이어서 진행(멱등)
        done += len(rows)
        print(f"  {done}/{len(texts)} 적재 완료", flush=True)
        if i + BATCH < len(texts):
            time.sleep(60)  # 무료 티어 100건/분 한도 회피 (배치=100)

    if skipped:
        print(f"[vectorize] L2 노름 이탈 skip {skipped}건 (재실행 시 재시도됨)")

    ensure_hnsw_index()

    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM question_embeddings")).scalar()
    print(f"[vectorize] 적재 완료: question_embeddings 총 {total}건")


if __name__ == "__main__":
    print(f"[vectorize] DB: {engine.url}")
    main()
