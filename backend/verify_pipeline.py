"""
적재 파이프라인 불변식 검증 게이트(CI 겸용). load → vectorize → refresh 후 실행.

V1~V5,V7 위반 시 exit 1(적재 실패 처리), V6 은 경고(다음 refresh 가 자가치유),
V8 은 캘리브레이션 리포트(수동 판단). Postgres + pgvector 전용.

실행 (backend/ 에서):
    python verify_pipeline.py        # exit code 로 합/불 판정
"""
import pathlib
import sys

# Windows 콘솔(cp949)에서 '—','≈' 등 비-cp949 문자 print 시 UnicodeEncodeError 크래시 방지.
# 출력 인코딩을 UTF-8(errors='replace')로 고정 — 검증 결과가 출력 문자 때문에 막히지 않게.
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
    engine,
)

K = 3
CURRENT_MODEL = EMBED_MODEL_NAME  # SSOT 파생값(:ss 포함)

# (id, 설명, SQL[위반행 COUNT], 기대, severity)  severity: fail | warn
_CHECKS = [
    (
        "V1", "임베딩 동기화(content_hash 일치)",
        "SELECT count(*) FROM question_embeddings e "
        "JOIN questions q ON q.question_id = e.question_id "
        "WHERE e.content_hash <> q.content_hash",
        "fail",
    ),
    (
        "V2", "임베딩 커버리지(active 전원 임베딩)",
        "SELECT count(*) FROM questions q "
        "LEFT JOIN question_embeddings e ON e.question_id = q.question_id "
        "WHERE q.status = 'active' AND e.question_id IS NULL",
        "fail",
    ),
    (
        "V3", f"행수 상한(이웃 ≤ {K}; rank CHECK 대체)",
        "SELECT count(*) FROM ("
        "  SELECT question_id FROM question_similar "
        "  GROUP BY question_id HAVING count(*) > :k) x",
        "fail",
    ),
    (
        "V4", "스테일 유사도(양측 임베딩 갱신 > similar.computed_at)",
        # similarity(A,B) 는 A·B 양쪽 임베딩에 의존 → 양측 모두 검사(단방향 누락 방지).
        # updated_at 은 tz-naive(UTC 기록) → AT TIME ZONE 'UTC' 로 timestamptz 와 정합 비교.
        "SELECT count(*) FROM question_similar s "
        "JOIN question_embeddings e1 ON e1.question_id = s.question_id "
        "JOIN question_embeddings e2 ON e2.question_id = s.similar_question_id "
        "WHERE (e1.updated_at AT TIME ZONE 'UTC') > s.computed_at "
        "   OR (e2.updated_at AT TIME ZONE 'UTC') > s.computed_at "
        "   OR s.computed_at IS NULL",
        "fail",
    ),
    (
        "V5", "모델 일관성(similar.model_name = 현행)",
        "SELECT count(*) FROM question_similar WHERE model_name <> :model",
        "fail",
    ),
    (
        "V6", "죽은 이웃(이웃이 active 아님)",
        "SELECT count(*) FROM question_similar s "
        "JOIN questions q ON q.question_id = s.similar_question_id "
        "WHERE q.status <> 'active'",
        "warn",
    ),
]


def _scalar(conn, sql: str) -> int:
    return conn.execute(text(sql), {"k": K, "model": CURRENT_MODEL}).scalar() or 0


def _check_v7(conn) -> int:
    """dedup_log: 6행 이상(시드 베이스라인) + kept FK 전행 유효."""
    total = conn.execute(text("SELECT count(*) FROM question_dedup_log")).scalar() or 0
    invalid = conn.execute(
        text(
            "SELECT count(*) FROM question_dedup_log d "
            "LEFT JOIN questions q ON q.question_id = d.kept_question_id "
            "WHERE q.question_id IS NULL"
        )
    ).scalar() or 0
    print(f"  V7  dedup_log 감사·FK 유효성              | rows={total} kept_FK_invalid={invalid}")
    # 시드 6행 미만이거나 깨진 FK 가 있으면 위반
    return (1 if total < 6 else 0) + invalid


def _report_v8(conn) -> None:
    rows = conn.execute(
        text(
            "SELECT removed_question_id, kept_question_id, similarity "
            "FROM question_dedup_log ORDER BY similarity"
        )
    ).fetchall()
    print("  V8  캘리브레이션 리포트(dedup similarity 분포 → T_dup 판단 근거):")
    if not rows:
        print("      (dedup_log 비어 있음)")
        return
    for r in rows:
        print(f"      {r[0]:<8} -> {r[1]:<10} sim={r[2]}")
    sims = [r[2] for r in rows if r[2] is not None]
    if sims:
        print(f"      min={min(sims)} max={max(sims)}  (manual 6쌍; B그룹 27쌍 비교는 별도 세트 — 범위 외)")


def main() -> int:
    if _is_sqlite or not HAS_PGVECTOR or QuestionEmbedding is None:
        raise SystemExit(
            "verify_pipeline 은 Postgres + pgvector 에서만 동작합니다 "
            "(question_embeddings·<=>·AT TIME ZONE 필요)."
        )
    failed, warned = [], []
    with engine.connect() as conn:
        for cid, desc, sql, sev in _CHECKS:
            n = _scalar(conn, sql)
            mark = "OK " if n == 0 else ("!! " if sev == "fail" else "~~ ")
            print(f"  {cid}  {desc:<40} | 위반 {n}행  {mark}")
            if n:
                (failed if sev == "fail" else warned).append(f"{cid}({n})")

        v7 = _check_v7(conn)
        if v7:
            failed.append(f"V7({v7})")

        _report_v8(conn)

    print()
    if failed:
        print(f"[verify] FAIL — 위반: {', '.join(failed)}"
              + (f" | 경고: {', '.join(warned)}" if warned else ""))
        return 1
    print(f"[verify] PASS — 전 불변식 통과"
          + (f" (경고: {', '.join(warned)} — 다음 refresh 자가치유)" if warned else ""))
    return 0


if __name__ == "__main__":
    print(f"[verify] DB: {engine.url}")
    sys.exit(main())
