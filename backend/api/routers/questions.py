import json as _json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request, status

from api.schemas.questions import QuestionDetail, QuestionListResponse, QuestionSummary

router = APIRouter(prefix="/questions", tags=["questions"])


def _safe_str(val) -> Optional[str]:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).strip()
    return s or None


def _get_has_sql(row) -> Optional[bool]:
    for key in ("has_sql_asset", "has_sql"):
        val = row.get(key)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            return bool(val)
    return None


def _parse_choices(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, str):
        try:
            return _json.loads(raw)
        except Exception:
            return None
    return raw


def _row_to_summary(row) -> QuestionSummary:
    return QuestionSummary(
        question_id=str(row.get("question_id", "")),
        chapter_name=str(row.get("chapter_name", "") or ""),
        subject_name=_safe_str(row.get("subject_name")),
        question_type=_safe_str(row.get("question_type")),
        difficulty_label=_safe_str(row.get("difficulty_label")),
        question_text=str(row.get("question_text", "") or ""),
        has_sql=_get_has_sql(row),
    )


def _row_to_detail(row) -> QuestionDetail:
    sql_raw = row.get("sql_code") or row.get("sql_content")
    correct_raw = row.get("correct_choice") if row.get("correct_choice") is not None else row.get("correct_answer")
    return QuestionDetail(
        question_id=str(row.get("question_id", "")),
        chapter_name=str(row.get("chapter_name", "") or ""),
        subject_name=_safe_str(row.get("subject_name")),
        question_type=_safe_str(row.get("question_type")),
        difficulty_label=_safe_str(row.get("difficulty_label")),
        question_text=str(row.get("question_text", "") or ""),
        choices=_parse_choices(row.get("choices")),
        correct_answer=int(correct_raw) if correct_raw is not None and str(correct_raw).isdigit() else correct_raw,
        explanation=_safe_str(row.get("explanation")),
        has_sql=_get_has_sql(row),
        sql_content=_safe_str(sql_raw),
    )


def _get_questions_df(request: Request):
    df = getattr(getattr(request.app.state, "models", None), "questions_df", None)
    if df is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="서버가 아직 초기화 중입니다. 잠시 후 다시 시도해주세요.",
        )
    return df


@router.get("", response_model=QuestionListResponse, summary="문제 목록 조회 (공개)")
def list_questions(
    request: Request,
    chapter_name: Optional[str] = Query(None, description="챕터명 필터"),
    difficulty: Optional[str] = Query(None, description="난이도 필터 (Easy/Medium/Hard)"),
    question_type: Optional[str] = Query(None, description="문제 유형 필터"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    df = _get_questions_df(request).copy()

    if chapter_name:
        df = df[df["chapter_name"].str.contains(chapter_name, na=False)]
    if difficulty:
        df = df[df["difficulty_label"] == difficulty]
    if question_type:
        df = df[df["question_type"] == question_type]

    total = len(df)
    page = df.iloc[offset: offset + limit]
    questions = [_row_to_summary(row) for _, row in page.iterrows()]
    return QuestionListResponse(total=total, questions=questions)


@router.get("/{question_id}", response_model=QuestionDetail, summary="문제 상세 조회 (공개)")
def get_question(question_id: str, request: Request):
    df = _get_questions_df(request)
    match = df[df["question_id"] == question_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"문제 {question_id}를 찾을 수 없습니다.")
    return _row_to_detail(match.iloc[0])
