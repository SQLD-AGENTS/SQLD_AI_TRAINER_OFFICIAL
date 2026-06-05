import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth import require_auth
from api.database import AnswerLog, get_db
from api.schemas.questions import AnswerSubmitRequest, AnswerSubmitResponse

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
    db.add(log)
    db.commit()

    return AnswerSubmitResponse(
        question_id=body.question_id,
        is_correct=is_correct,
        correct_answer=correct_answer,
        message="정답입니다!" if is_correct else "오답입니다. AI 해설을 확인해보세요.",
    )
