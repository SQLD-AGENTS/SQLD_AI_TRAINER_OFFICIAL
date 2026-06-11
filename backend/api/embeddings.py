"""
Gemini 임베딩 헬퍼 — 적재(배치/단건)와 검색 질의에서 공용으로 쓰는 단일 진입점.

task_type 은 단일 원천 EMBED_TASK_TYPE(SEMANTIC_SIMILARITY) — 문항↔문항 대칭 유사도라
질의/문서를 구분하지 않는다. 모델 id·저장명은 EMBED_MODEL / EMBED_MODEL_NAME(파생) 참조.

설계 의도(읽기/쓰기 분리):
- 쓰기: question_embeddings 에 저장할 문제 임베딩 → Gemini 호출 필요
    · 배치 백필     : vectorize_questions.py (기존 전체 문제)
    · 단건(플라이휠): 생성·검수 통과 문제를 DB 적재 직후 upsert_question_embedding() 로 즉시 임베딩
- 읽기(검색): 이미 적재된 문제끼리의 유사 검색은 저장된 임베딩을 그대로 SQL(cosine)로 비교하므로
    Gemini 호출이 필요 없음. (explainer.retrieve_similar 는 이 모듈을 호출하지 않는다)
- 자유 텍스트 검색: DB에 없는 텍스트는 embed_query() 사용(동일 task_type, 선택).

1536차원은 L2 정규화가 필요(3072 외 차원). 정규화 벡터 + pgvector cosine(<=>) 조합으로 검색.
Postgres + pgvector 전용. 로컬 SQLite 에서는 upsert 가 no-op(False) 로 안전하게 강등된다.
"""
import os
from typing import List

import numpy as np

from api.database import EMBED_DIM, EMBED_MODEL, EMBED_MODEL_NAME, EMBED_TASK_TYPE


def _client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 미설정 — 임베딩을 생성할 수 없습니다.")
    from google import genai

    return genai.Client(api_key=api_key)


def embed_texts(
    texts: List[str], task_type: str = EMBED_TASK_TYPE, client=None
) -> List[list]:
    """텍스트 목록 → L2 정규화된 EMBED_DIM(1536) 차원 임베딩 목록.

    task_type 기본값은 SSOT 인 EMBED_TASK_TYPE(SEMANTIC_SIMILARITY). API 에 넘기는 모델은
    'base' EMBED_MODEL(태그 없는 실제 모델 id) — DB 저장용 파생 EMBED_MODEL_NAME 과 구분.
    """
    from google.genai import types

    client = client or _client()
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(
            task_type=task_type, output_dimensionality=EMBED_DIM
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


def embed_query(text: str, client=None) -> list:
    """자유 텍스트 단건 임베딩. 저장 임베딩과 동일 task_type(EMBED_TASK_TYPE)으로 같은
    벡터 공간에 매핑한다 — SEMANTIC_SIMILARITY 는 대칭이라 질의/문서를 구분하지 않음."""
    return embed_texts([text], client=client)[0]


def upsert_question_embedding(question_id: str, text: str, client=None) -> bool:
    """신규/수정 문제 1건을 임베딩해 question_embeddings 에 upsert.

    플라이휠: 생성·검수 통과 문제를 questions 에 적재한 직후 이 함수를 호출하면
    그 문제가 즉시 유사도 검색 대상이 된다(인덱스 재빌드 불필요).
    Postgres + pgvector 전용 — 로컬 SQLite/미지원 환경에서는 False 반환(no-op).
    """
    from api.database import (
        HAS_PGVECTOR,
        QuestionEmbedding,
        _is_sqlite,
        engine,
    )

    if _is_sqlite or not HAS_PGVECTOR or QuestionEmbedding is None:
        return False

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    vec = embed_texts([text])[0]
    stmt = pg_insert(QuestionEmbedding.__table__).values(
        question_id=str(question_id), embedding=vec, model_name=EMBED_MODEL_NAME
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["question_id"],
        set_={
            "embedding": stmt.excluded.embedding,
            "model_name": stmt.excluded.model_name,
        },
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return True
