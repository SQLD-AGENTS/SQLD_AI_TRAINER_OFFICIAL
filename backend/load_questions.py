"""
문제 마스터(datasets/json/*.json)를 DB의 questions 테이블에 적재한다.

- json_parser.parse_all() + features.add_features() 로 runtime DataFrame과 동일한 19컬럼 + choices 생성
  (ML 학습에 쓰인 questions.csv 와 동일 로직 → 데이터 불일치 방지)
- session.merge() 기반 upsert: 재실행해도 안전(idempotent)하고,
  answer_logs FK가 걸려 있어도 행을 지우지 않으므로 깨지지 않음

실행 (반드시 backend/ 디렉터리에서 → api.* 임포트가 동작해야 함):
    cd backend
    python load_questions.py

DATABASE_URL 환경변수가 있으면 그 DB(Postgres)로, 없으면 로컬 SQLite로 적재한다.
runtime(main.py lifespan)에서도 questions 가 비어 있으면 load() 를 1회 자동 호출한다.
"""
import json
import pathlib
import sys

# Windows 콘솔(cp949) 비-cp949 문자 print 크래시 방지 — UTF-8(errors='replace') 고정.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

# json_parser / features (backend/src/data) 임포트 경로 추가
_SRC_DATA = pathlib.Path(__file__).resolve().parent / "src" / "data"
if str(_SRC_DATA) not in sys.path:
    sys.path.insert(0, str(_SRC_DATA))

import json_parser  # noqa: E402
from features import add_features  # noqa: E402

from sqlalchemy import func  # noqa: E402
from api.database import (  # noqa: E402
    AnswerLog,
    Question,
    QuestionDedupLog,
    SessionLocal,
    _is_sqlite,
    create_tables,
    engine,
)


# ---------------------------------------------------------------------------
# 원본 JSON 위치 보정
#   json_parser.JSON_DIR 는 모듈 기준 상대경로(backend/datasets/json)라 실행 환경에 따라
#   어긋날 수 있어, 런타임(state.py)·Dockerfile 과 동일한 '루트/datasets/json' 으로 맞춘다.
# ---------------------------------------------------------------------------
def _resolve_json_dir() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parent.parent / "datasets" / "json",  # repo 루트 또는 컨테이너 /app
        here.parent / "datasets" / "json",          # 혹시 모를 backend/datasets/json
    ]
    for p in candidates:
        if p.exists() and any(p.glob("*.json")):
            return p
    raise SystemExit(
        "datasets/json 을 찾지 못했습니다. JSON 파일 위치를 확인하세요.\n"
        f"  탐색 경로: {[str(c) for c in candidates]}"
    )


def _nan_to_none(v):
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    return v


def _to_int(v):
    v = _nan_to_none(v)
    return int(v) if v is not None else None


def _assets_value(v):
    """assets 정규화 — 원본 list 그대로(JSONB 저장), 혹시 JSON 문자열이면 역직렬화.

    pandas 셀이 list 라 _nan_to_none(pd.isna)을 쓰면 'ambiguous' 에러 → 전용 처리.
    """
    if v is None:
        return None
    if isinstance(v, float):  # NaN
        return None
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return None
    return v  # list/dict 그대로


def build_dataframe() -> pd.DataFrame:
    json_parser.JSON_DIR = _resolve_json_dir()
    df = add_features(json_parser.parse_all())
    assert df["question_id"].is_unique, "question_id 중복 발생"
    return df


def _row_to_values(r: pd.Series) -> dict:
    # choices: parse_all()이 JSON 문자열로 생성 → dict/list 로 역직렬화해 JSONB 에 저장
    raw_choices = r.get("choices")
    if isinstance(raw_choices, str):
        try:
            choices = json.loads(raw_choices)
        except Exception:
            choices = None
    else:
        choices = raw_choices if raw_choices is not None else None

    # provenance(source/status/generated_from/fitness_score/created_at)는 컬럼 기본값에 위임
    return {
        "question_id": str(r["question_id"]),
        "subject_id": _to_int(r["subject_id"]),
        "chapter_id": _to_int(r["chapter_id"]),
        "chapter_name": _nan_to_none(r.get("chapter_name")) or "",
        "question_number": _to_int(r["question_number"]),
        "book_section": _nan_to_none(r.get("book_section")) or "",
        "book_question_number": _to_int(r.get("book_question_number")),
        "question_type": _nan_to_none(r.get("question_type")) or "",
        "question_text": _nan_to_none(r.get("question_text")) or "",
        "sql_code": _nan_to_none(r.get("sql_code")) or "",
        "has_sql_asset": bool(r.get("has_sql_asset")),
        "choice_count": _to_int(r.get("choice_count")) or 0,
        "choice_kinds": _nan_to_none(r.get("choice_kinds")) or "",
        "choices": choices,
        "correct_choice": _to_int(r.get("correct_choice")),
        "explanation": _nan_to_none(r.get("explanation")) or "",
        "question_type_encoded": _to_int(r.get("question_type_encoded")),
        "choice_kind_complexity": _to_int(r.get("choice_kind_complexity")) or 0,
        "difficulty": _to_int(r.get("difficulty")) or 0,
        "difficulty_label": _nan_to_none(r.get("difficulty_label")) or "",
        # v4: 원본 자산 무손실 + 시험지 과목 + 임베딩 동기화 키
        "assets": _assets_value(r.get("assets")),
        "exam_subject": _to_int(r.get("exam_subject")),
        "content_hash": _nan_to_none(r.get("content_hash")) or "",
    }


def _row_to_question(r: pd.Series) -> Question:
    return Question(**_row_to_values(r))


def load(df: pd.DataFrame) -> int:
    """questions 적재 (idempotent).

    - SQLite(로컬): ORM merge 루프
    - Postgres(Railway): 청크 단위 ON CONFLICT upsert → 행별 왕복(594회)을 ~3회로 줄여
      프록시 SSL 끊김('unexpected eof') 회피 + 고속
    """
    create_tables()  # 테이블/확장 보장 (있으면 무시)
    rows = [_row_to_values(r) for _, r in df.iterrows()]
    if not rows:
        return 0

    if _is_sqlite:
        with SessionLocal() as db:
            for d in rows:
                db.merge(Question(**d))
            db.commit()
        return len(rows)

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    content_cols = [c for c in rows[0] if c != "question_id"]
    chunk = 100
    processed = 0
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            batch = rows[i : i + chunk]
            stmt = pg_insert(Question.__table__).values(batch)
            # 변경 추적: 재적재 시 updated_at 갱신(ORM onupdate 는 core 경로에서 미발화)
            set_ = {c: stmt.excluded[c] for c in content_cols}
            set_["updated_at"] = func.now()
            stmt = stmt.on_conflict_do_update(
                index_elements=["question_id"], set_=set_
            )
            conn.execute(stmt)
            processed += len(batch)
    return processed


# ---------------------------------------------------------------------------
# dedup_log 시드 — 모의고사 병합 시 하드 삭제한 6쌍의 감사·캘리브레이션 이력
#   (removed_section, removed_num) 은 합성 식별자(원행 부재·FK 없음)로 라벨만 보존,
#   kept 는 (book_section, book_question_number) 좌표로 실제 question_id 를 DB 에서 해석한다
#   — 하드코딩 금지(글로벌 chapter 번호 체계가 바뀌어도 시드가 살아남도록).
# ---------------------------------------------------------------------------
DEDUP_SEED = [
    # removed_label, kept_section, kept_num, similarity, comment
    ("M55-10", "I", 23, 0.711),   # 관계 차수
    ("M56-29", "II", 32, 0.978),  # SQL 실행 순서
    ("M56-31", "M55", 7, 0.348),  # ACID (개념 중복 — 임계 하한 증거)
    ("M57-16", "II", 96, 0.768),  # INTERSECT
    ("M58-10", "M55", 7, 0.714),  # ACID
    ("M58-26", "II", 10, 0.957),  # NULL 조회
]


def seed_dedup_log() -> int:
    """dedup 6쌍을 question_dedup_log 에 멱등 시드(확정 5컬럼). load() 이후 호출 — kept FK 필요.

    kept_question_id 는 (book_section, book_question_number) 로 해석(하드코딩 금지).
    멱등: removed_question_id PK 가 이미 있으면 건너뜀.
    """
    inserted, skipped = 0, []
    with SessionLocal() as db:
        for removed_label, sec, num, sim in DEDUP_SEED:
            kept = (
                db.query(Question.question_id)
                .filter(
                    Question.book_section == sec,
                    Question.book_question_number == num,
                )
                .scalar()
            )
            if kept is None:
                skipped.append(f"{sec}-{num}(removed {removed_label})")
                continue
            if db.get(QuestionDedupLog, removed_label) is not None:
                continue  # 멱등
            db.add(
                QuestionDedupLog(
                    removed_question_id=removed_label,
                    kept_question_id=kept,
                    similarity=sim,
                    method="manual",
                )
            )
            inserted += 1
        db.commit()
    if skipped:
        print(f"[dedup-seed][warn] kept 좌표 미해석 {len(skipped)}건 → 건너뜀: {skipped}")
    return inserted


def prune_orphans(current_ids: set) -> int:
    """현재 소스 JSON 에 없는 original 문항을 정리 — 데이터셋 편집 후 고아 누적 방지.

    load() 가 upsert-only(삭제 안 함)라, 데이터셋에서 문항이 빠지면 구 행이 영구 잔류하며
    서빙(status='active')·임베딩·유사도(question_similar)를 오염시킨다. 이를 정리한다.

    안전장치:
    - source='generated' 제외: 플라이휠 생성 문항은 JSON 파생이 아니므로 보호(오삭제 방지).
    - answer_logs 참조 행: FK(RESTRICT)라 하드 삭제 불가 → status='retired' 로 강등(서빙 제외).
    - 그 외 고아: 하드 삭제(question_embeddings·question_similar 는 ondelete=CASCADE 동반 정리).
    - CLI(__main__)에서만 호출 — 런타임 auto-seed 경로는 prune 하지 않음(오삭제 사고 차단).
    """
    with SessionLocal() as db:
        db_ids = {
            qid
            for (qid,) in db.query(Question.question_id)
            .filter(Question.source == "original")
            .all()
        }
        orphan_ids = db_ids - current_ids
        if not orphan_ids:
            return 0
        referenced = {
            qid
            for (qid,) in db.query(AnswerLog.question_id)
            .filter(AnswerLog.question_id.in_(orphan_ids))
            .distinct()
            .all()
        }
        to_retire = orphan_ids & referenced
        to_delete = orphan_ids - referenced
        if to_retire:
            db.query(Question).filter(Question.question_id.in_(to_retire)).update(
                {"status": "retired"}, synchronize_session=False
            )
        if to_delete:
            db.query(Question).filter(Question.question_id.in_(to_delete)).delete(
                synchronize_session=False
            )
        db.commit()
    print(
        f"[prune] 고아 정리: 삭제 {len(to_delete)}건"
        + (f", retire(answer_logs 참조) {len(to_retire)}건" if to_retire else "")
    )
    return len(to_delete) + len(to_retire)


if __name__ == "__main__":
    print(f"[load_questions] DB: {engine.url}")
    df = build_dataframe()
    print(f"[load_questions] 파싱된 문제 수: {len(df)}")

    processed = load(df)

    pruned = prune_orphans(set(df["question_id"]))

    seeded = seed_dedup_log()

    with SessionLocal() as db:
        total = db.query(Question).count()
        dedup_total = db.query(QuestionDedupLog).count()
    print(
        f"[load_questions] 적재 완료: {processed}건 처리, questions 총 {total}건, "
        f"dedup_log 시드 +{seeded}건(총 {dedup_total}건)"
    )
