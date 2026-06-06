"""
questions 임베딩을 Google Gemini(gemini-embedding-001)로 생성해 question_embeddings(pgvector)에 적재.

- 차원: 1536 (output_dimensionality; 3072 동급 품질 + pgvector HNSW 인덱스(≤2000) 가능)
- gemini-embedding-001 은 3072 외 차원에서 L2 정규화가 필요 → 수동 정규화
- task_type=RETRIEVAL_DOCUMENT (저장용 문서 임베딩; 검색 질의는 RETRIEVAL_QUERY 사용)
- 멱등: 아직 임베딩 안 된 문제만 처리. Postgres + pgvector 전용.

환경변수:
    GEMINI_API_KEY   (필수)  Google AI Studio 키
    DATABASE_URL     (필수)  Railway Postgres (pgvector 템플릿)

실행 (backend/ 에서):
    $env:GEMINI_API_KEY = "..."
    $env:DATABASE_URL   = "postgresql://...proxy.rlwy.net:.../railway"
    python vectorize_questions.py
"""
import os
import pathlib
import time

from dotenv import load_dotenv

# 저장소 루트 .env 로드 → GEMINI_API_KEY 등. (DATABASE_URL 은 셸 환경 우선: override=False)
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from api.database import (  # noqa: E402
    EMBED_DIM,
    EMBED_MODEL_NAME,
    HAS_PGVECTOR,
    QuestionEmbedding,
    _is_sqlite,
    create_tables,
    engine,
)

TASK_TYPE = "RETRIEVAL_DOCUMENT"
BATCH = 100  # Gemini embed_content 배치 크기


def _doc_text(row) -> str:
    """임베딩 대상 텍스트: 문제 본문 + 해설."""
    q = str(row.get("question_text") or "")
    ex = str(row.get("explanation") or "")
    return (q + " " + ex).strip()


def _fetch_unembedded() -> pd.DataFrame:
    """아직 임베딩되지 않은 문제만 반환."""
    sql = """
        SELECT q.question_id, q.question_text, q.explanation
        FROM questions q
        LEFT JOIN question_embeddings e ON e.question_id = q.question_id
        WHERE e.question_id IS NULL
        ORDER BY q.question_id
    """
    return pd.read_sql_query(sql, engine)


def _embed_batch(client, texts: list) -> list:
    """Gemini 임베딩 호출 → L2 정규화된 (len(texts), EMBED_DIM) 리스트."""
    from google.genai import types

    resp = client.models.embed_content(
        model=EMBED_MODEL_NAME,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=TASK_TYPE,
            output_dimensionality=EMBED_DIM,
        ),
    )
    out = []
    for emb in resp.embeddings:
        v = np.asarray(emb.values, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm  # 1536차원은 수동 L2 정규화 필요(3072 외)
        out.append(v.tolist())
    return out


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
    texts = [_doc_text(r) for _, r in df.iterrows()]
    print(
        f"[vectorize] 대상 {len(texts)}건 → Gemini({EMBED_MODEL_NAME}, dim={EMBED_DIM}) 임베딩 시작 "
        f"(무료 티어 100건/분 → 배치마다 throttle)..."
    )

    done = 0
    for i in range(0, len(texts), BATCH):
        vecs = _embed_with_retry(client, texts[i : i + BATCH])
        rows = []
        for qid, v in zip(qids[i : i + BATCH], vecs):
            assert len(v) == EMBED_DIM, f"차원 불일치: {len(v)} != {EMBED_DIM}"
            rows.append(
                {"question_id": str(qid), "embedding": v, "model_name": EMBED_MODEL_NAME}
            )
        _upsert(rows)  # 배치 단위 저장 → 중단돼도 재실행 시 이어서 진행(멱등)
        done += len(rows)
        print(f"  {done}/{len(texts)} 적재 완료", flush=True)
        if i + BATCH < len(texts):
            time.sleep(60)  # 무료 티어 100건/분 한도 회피 (배치=100)

    ensure_hnsw_index()

    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM question_embeddings")).scalar()
    print(f"[vectorize] 적재 완료: question_embeddings 총 {total}건")


if __name__ == "__main__":
    print(f"[vectorize] DB: {engine.url}")
    main()
