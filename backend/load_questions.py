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

import pandas as pd

# json_parser / features (backend/src/data) 임포트 경로 추가
_SRC_DATA = pathlib.Path(__file__).resolve().parent / "src" / "data"
if str(_SRC_DATA) not in sys.path:
    sys.path.insert(0, str(_SRC_DATA))

import json_parser  # noqa: E402
from features import add_features  # noqa: E402

from api.database import Question, SessionLocal, _is_sqlite, create_tables, engine  # noqa: E402


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
            stmt = stmt.on_conflict_do_update(
                index_elements=["question_id"],
                set_={c: stmt.excluded[c] for c in content_cols},
            )
            conn.execute(stmt)
            processed += len(batch)
    return processed


if __name__ == "__main__":
    print(f"[load_questions] DB: {engine.url}")
    df = build_dataframe()
    print(f"[load_questions] 파싱된 문제 수: {len(df)}")

    processed = load(df)

    with SessionLocal() as db:
        total = db.query(Question).count()
    print(f"[load_questions] 적재 완료: {processed}건 처리, questions 테이블 총 {total}건")
