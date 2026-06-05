import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth import require_auth
from api.database import AnswerLog, get_db
from api.schemas.predict import PredictRequest, PredictResponse

router = APIRouter(prefix="/predict", tags=["predict"])


def _risk_level(prob: float) -> str:
    if prob >= 0.65:
        return "high"
    if prob >= 0.4:
        return "medium"
    return "low"


def _build_feature_vector(
    user_id: str,
    question_id: str,
    logs: list,
    questions_df: pd.DataFrame,
    feature_names: list,
) -> np.ndarray:
    """
    predictor 학습 시 사용한 피처와 동일한 구조로 단건 피처 벡터 생성.
    feature_names 에 없는 피처는 0으로 채운다.
    """
    q_df = questions_df.set_index("question_id")
    q_row = q_df.loc[question_id] if question_id in q_df.index else None

    # 유저 챕터 정확도
    user_chapter_acc = 0.5  # 기본값
    if logs and q_row is not None:
        chapter = str(q_row.get("chapter_name", ""))
        ch_logs = [
            l for l in logs
            if l.question_id in q_df.index
            and str(q_df.loc[l.question_id].get("chapter_name", "")) == chapter
        ]
        if ch_logs:
            user_chapter_acc = sum(l.is_correct for l in ch_logs) / len(ch_logs)

    has_sql = int(bool(q_row.get("has_sql", False))) if q_row is not None else 0
    difficulty_map = {"Easy": 0, "Medium": 1, "Hard": 2}
    difficulty = difficulty_map.get(
        str(q_row.get("difficulty_label", "Medium")), 1
    ) if q_row is not None else 1

    feature_dict = {
        "user_chapter_acc": user_chapter_acc,
        "has_sql": has_sql,
        "difficulty_encoded": difficulty,
        "total_attempts": len(logs),
    }

    vec = np.array([feature_dict.get(f, 0.0) for f in feature_names], dtype=float)
    return vec.reshape(1, -1)


@router.post("", response_model=PredictResponse, summary="오답 확률 예측 (인증 필요)")
def predict_error(
    body: PredictRequest,
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    현재 사용자의 학습 이력을 기반으로 해당 문제의 오답 확률을 예측합니다.
    이력이 없거나 모델 로드 실패 시 통계 기반 fallback을 반환합니다.
    """
    state = request.app.state.models
    user_id = user["sub"]

    df = state.questions_df
    if not (df["question_id"] == body.question_id).any():
        raise HTTPException(status_code=404, detail=f"문제 {body.question_id}를 찾을 수 없습니다.")

    logs = db.query(AnswerLog).filter(AnswerLog.user_id == user_id).all()

    state.load_predictor_if_needed()
    # 모델 없으면 통계 기반 fallback
    if state.predictor_model is None or state.predictor_feature_names is None:
        total = len(logs)
        correct = sum(l.is_correct for l in logs)
        user_acc = correct / total if total > 0 else 0.5
        prob = round(1.0 - user_acc, 4)
        return PredictResponse(
            question_id=body.question_id,
            error_probability=prob,
            risk_level=_risk_level(prob),
            message=f"통계 기반 예측 (전체 정답률 {user_acc:.1%} 기준)",
            source="fallback",
        )

    try:
        vec = _build_feature_vector(
            user_id,
            body.question_id,
            logs,
            state.questions_df,
            state.predictor_feature_names,
        )
        prob = float(state.predictor_model.predict_proba(vec)[0][1])
        prob = round(prob, 4)
        return PredictResponse(
            question_id=body.question_id,
            error_probability=prob,
            risk_level=_risk_level(prob),
            message=f"오답 확률 {prob:.1%} — {'주의가 필요합니다' if prob >= 0.5 else '도전해보세요'}",
            source="model",
        )
    except Exception as e:
        # 피처 불일치 등 예외 시 fallback
        return PredictResponse(
            question_id=body.question_id,
            error_probability=0.5,
            risk_level="medium",
            message=f"예측 중 오류 발생 — 기본값 반환 ({e})",
            source="fallback",
        )
