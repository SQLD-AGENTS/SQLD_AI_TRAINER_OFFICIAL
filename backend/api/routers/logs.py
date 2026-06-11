import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from api.auth import require_auth
from api.database import AnswerLog, get_db
from api.schemas.questions import AnswerSubmitRequest, AnswerSubmitResponse, CheckSolvedResponse, SolvedSummaryResponse

router = APIRouter(prefix="/logs", tags=["logs"])


@router.post("", response_model=AnswerSubmitResponse, summary="문제 풀이 결과 저장 (인증 필요)")
def submit_answer(
    body: AnswerSubmitRequest,
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    인증된 사용자의 풀이 결과를 DB에 저장합니다.
    정답 여부를 반환하며, 이후 /recommend, /progress, /predict 에서 활용됩니다.
    게스트 토큰으로는 호출할 수 없습니다.
    """
    df = request.app.state.models.questions_df
    match = df[df["question_id"] == body.question_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"문제 {body.question_id}를 찾을 수 없습니다.")

    row = match.iloc[0]
    _raw = row.get("correct_choice") if row.get("correct_choice") is not None else row.get("correct_answer")
    correct_answer = int(_raw) if _raw is not None else None

    # 선택지 제출이 없을 경우 정답 여부를 알 수 없으므로 오답 처리
    is_correct = False
    if body.selected_answer is not None and correct_answer is not None:
        try:
            is_correct = str(body.selected_answer).strip() == str(correct_answer).strip()
        except Exception:
            is_correct = False

    log = AnswerLog(
        user_id=user["sub"],
        question_id=body.question_id,
        is_correct=is_correct,
        solve_time_sec=body.solve_time_sec,
        logged_at=datetime.datetime.utcnow(),
    )
    try:
        db.add(log)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="풀이 결과 저장 중 오류가 발생했습니다.")

    return AnswerSubmitResponse(
        question_id=body.question_id,
        is_correct=is_correct,
        correct_answer=correct_answer,
        message="정답입니다!" if is_correct else "오답입니다. AI 해설을 확인해보세요.",
    )


@router.get("/solved", response_model=SolvedSummaryResponse, summary="내가 푼 문제 요약 (인증 필요)")
def get_solved_summary(
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    현재 로그인 사용자가 1회 이상 시도한 문제 ID와 정답을 맞춘 문제 ID를 반환합니다.
    """
    user_id = user["sub"]

    solved_rows = (
        db.query(AnswerLog.question_id)
        .filter(AnswerLog.user_id == user_id)
        .distinct()
        .all()
    )
    correct_rows = (
        db.query(AnswerLog.question_id)
        .filter(AnswerLog.user_id == user_id, AnswerLog.is_correct == True)  # noqa: E712
        .distinct()
        .all()
    )

    return SolvedSummaryResponse(
        solved_ids=[r[0] for r in solved_rows],
        correct_ids=[r[0] for r in correct_rows],
    )


@router.get("/check/{question_id}", response_model=CheckSolvedResponse, summary="특정 문제 풀이 기록 확인 (인증 필요)")
def check_solved(
    question_id: str,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    user_id = user["sub"]
    log = (
        db.query(AnswerLog)
        .filter(AnswerLog.user_id == user_id, AnswerLog.question_id == question_id)
        .order_by(AnswerLog.logged_at.desc())
        .first()
    )
    if log is None:
        return CheckSolvedResponse(is_solved=False, is_correct=None)
    return CheckSolvedResponse(is_solved=True, is_correct=log.is_correct)
