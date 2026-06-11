"""
question_similar(유사도 사전 매핑) 전체 리프레시 — upsert-then-prune 단일 트랜잭션.

파이프라인 3단계(load → vectorize → refresh). active 문항 풀에서 문항별 top-k 이웃을
pgvector cosine(<=>)으로 계산해 question_similar 에 멱등 반영한다. /explain 무쿼리화·추천
쿨다운·dedup 사전필터가 이 테이블을 소비한다. Postgres + pgvector 전용.

설계(파이프라인 MD §3-1 + 감사 함정 2건 반영):
- 단일 트랜잭션: 중간에 '이웃 0개' 상태 없음(원자적 교체). 이웃 불변 행은 무처치(WAL 절약).
- ★ WHERE 1 - dist > 0 : 코사인거리 ≥ 1(유사도 ≤ 0) 쌍을 제외 → ck_qsim_similarity
  (similarity > 0 AND <= 1) CHECK 위반으로 트랜잭션 전체가 롤백되는 것을 방지.
- ★ computed_at = now() 명시 : raw INSERT 라 ORM 파이썬 default 가 안 먹는다(NULL 방지).
- prune: 이번 계산에 없는 구 이웃(=retired/pending 전이분 등)을 자동 청소.

실행 (backend/ 에서):
    python refresh_similarities.py
"""
import pathlib
import sys

# Windows 콘솔(cp949) 비-cp949 문자 print 크래시 방지 — UTF-8(errors='replace') 고정.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import text  # noqa: E402

from api.database import (  # noqa: E402
    EMBED_MODEL_NAME,
    HAS_PGVECTOR,
    QuestionEmbedding,
    _is_sqlite,
    create_tables,
    engine,
)

K = 3  # 문항별 이웃 수(top-k). 확장 시 이 숫자만 변경.

# upsert-then-prune 단일 트랜잭션. :k 바인딩.
_REFRESH_SQL = text(
    """
    WITH fresh AS (
        SELECT e.question_id,
               t.question_id  AS similar_question_id,
               1 - t.dist     AS similarity
        FROM question_embeddings e
        JOIN questions q ON q.question_id = e.question_id AND q.status = 'active'
        JOIN LATERAL (
            SELECT e2.question_id, e.embedding <=> e2.embedding AS dist
            FROM question_embeddings e2
            JOIN questions q2 ON q2.question_id = e2.question_id AND q2.status = 'active'
            WHERE e2.question_id <> e.question_id
              AND e2.model_name = :model      -- ★ 동일 모델 공간만(이종 벡터 혼입 차단)
            ORDER BY e.embedding <=> e2.embedding
            LIMIT :k
        ) t ON true
        WHERE e.model_name = :model           -- ★ 현행 모델만
          AND 1 - t.dist > 0                  -- ★ ck_qsim_similarity 방어
    ),
    upserted AS (
        INSERT INTO question_similar
            (question_id, similar_question_id, similarity, model_name, computed_at)
        SELECT question_id, similar_question_id, similarity, :model, now()  -- ★ 모델 상수·명시
        FROM fresh
        ON CONFLICT (question_id, similar_question_id) DO UPDATE
            SET similarity = EXCLUDED.similarity,
                model_name = EXCLUDED.model_name,
                computed_at = now()
        RETURNING question_id, similar_question_id
    )
    DELETE FROM question_similar s
    WHERE NOT EXISTS (
        SELECT 1 FROM upserted u
        WHERE u.question_id = s.question_id
          AND u.similar_question_id = s.similar_question_id
    )
    """
)


def refresh_all() -> int:
    """풀 리프레시 1회. prune 된 행 수를 반환(단일 트랜잭션).

    현행 모델(EMBED_MODEL_NAME)의 임베딩만 대상 — 스테일 모델 벡터가 이종 공간에서
    거리계산에 끼거나 model_name 이 섞이는 것을 SQL 레벨에서 차단(verify V5 정합).
    """
    with engine.begin() as conn:
        result = conn.execute(_REFRESH_SQL, {"k": K, "model": EMBED_MODEL_NAME})
        return result.rowcount or 0


def refresh_one(question_id: str) -> int:
    """단건 플라이휠 훅 — 현 규모(수백)에선 풀 리프레시로 갈음.

    시그니처만 분리해 둔다(조기 최적화 회피). 후일 본인 top-k + 역방향 무효화로 교체.
    """
    return refresh_all()


def _report() -> None:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM question_similar")).scalar()
        active = conn.execute(
            text("SELECT count(*) FROM questions WHERE status = 'active'")
        ).scalar()
        # 이웃 < K (방어절·작은 풀로 인한 미달 — 정상이나 가시화)
        under_k = conn.execute(
            text(
                "SELECT count(*) FROM ("
                "  SELECT question_id FROM question_similar"
                "  GROUP BY question_id HAVING count(*) < :k"
                ") x"
            ),
            {"k": K},
        ).scalar()
        # 이웃이 아예 없는 active 문항
        no_neighbor = conn.execute(
            text(
                "SELECT count(*) FROM questions q "
                "WHERE q.status = 'active' AND NOT EXISTS ("
                "  SELECT 1 FROM question_similar s WHERE s.question_id = q.question_id)"
            )
        ).scalar()
    print(
        f"[refresh] question_similar 총 {total}행 | active {active}문항 "
        f"(기대~{active * K}) | 이웃<{K} {under_k}문항 | 이웃0 {no_neighbor}문항"
    )
    if under_k or no_neighbor:
        print(
            "  (이웃<K/0 은 WHERE 1-dist>0 방어 또는 작은 active 풀에 의한 정상 미달 — 경고만)"
        )


def main() -> None:
    if _is_sqlite or not HAS_PGVECTOR or QuestionEmbedding is None:
        raise SystemExit(
            "refresh_similarities 는 Postgres + pgvector 에서만 동작합니다 "
            "(LATERAL + <=> 연산자 필요).\nDATABASE_URL 을 Railway Postgres 로 설정하세요."
        )
    create_tables()  # question_similar 보장
    pruned = refresh_all()
    print(f"[refresh] 풀 리프레시 완료 (prune {pruned}행)")
    _report()


if __name__ == "__main__":
    print(f"[refresh] DB: {engine.url}")
    main()
