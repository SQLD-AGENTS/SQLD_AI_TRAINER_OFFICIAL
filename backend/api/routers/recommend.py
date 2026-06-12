import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth import require_auth
from api.database import AnswerLog, get_db
from api.schemas.recommend import RecommendRequest, RecommendResponse, RecommendedQuestion

router = APIRouter(prefix="/recommend", tags=["recommend"])


def _get_user_logs_df(user_id: str, db: Session, questions_df: pd.DataFrame) -> pd.DataFrame:
    """SQLite의 실제 유저 로그를 추천 함수가 기대하는 DataFrame 형식으로 변환."""
    logs = db.query(AnswerLog).filter(AnswerLog.user_id == user_id).all()
    if not logs:
        return pd.DataFrame(columns=["user_id", "question_id", "is_correct", "solve_time_sec"])

    rows = [
        {
            "user_id": l.user_id,
            "question_id": l.question_id,
            "is_correct": int(l.is_correct),
            "solve_time_sec": l.solve_time_sec or 0.0,
        }
        for l in logs
    ]
    df = pd.DataFrame(rows)
    # chapter_name 병합 (추천기에서 약점 챕터 분석에 필요)
    df = df.merge(
        questions_df[["question_id", "chapter_name", "chapter_id"]],
        on="question_id",
        how="left",
    )
    return df


def _build_dkt_probs(state, user_logs_df: pd.DataFrame):
    """DKT로 각 문제에 대한 P(correct) 계산."""
    if state.dkt_model is None or state.dkt_question_ids is None:
        return None
    if user_logs_df.empty:
        return None

    try:
        import sys, pathlib
        _src = pathlib.Path(__file__).resolve().parent.parent.parent / "src" / "models"
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))

        from knowledge_tracer import predict_next

        q_to_idx = {qid: i for i, qid in enumerate(state.dkt_question_ids)}
        user_sequence = {
            "user_id": user_logs_df["user_id"].iloc[0],
            "question_ids": user_logs_df["question_id"].tolist(),
            "is_corrects": user_logs_df["is_correct"].tolist(),
        }
        probs = predict_next(state.dkt_model, user_sequence, q_to_idx, state.device)
        return {qid: float(probs[i]) for i, qid in enumerate(state.dkt_question_ids)}
    except Exception as e:
        print(f"[recommend] DKT 예측 실패: {e}")
        return None


@router.post("/{user_id}", response_model=RecommendResponse, summary="개인화 문제 추천 (인증 필요)")
def recommend_questions(
    user_id: str,
    body: RecommendRequest,
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    DKT ZPD 필터가 적용된 개인화 추천.
    - 인증된 사용자 본인의 추천만 조회 가능합니다.
    - 풀이 이력이 없으면 챕터 1 입문 문제를 반환합니다.
    """
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="본인의 추천만 조회할 수 있습니다.")

    state = request.app.state.models
    state.load_recommender_if_needed()
    if state.recommender is None:
        raise HTTPException(status_code=503, detail="추천 모델이 초기화되지 않았습니다.")

    user_logs_df = _get_user_logs_df(user_id, db, state.questions_df)

    # 풀이 이력이 없는 신규 유저 — 챕터 1 Easy 문제 반환
    if user_logs_df.empty:
        starter = (
            state.questions_df[state.questions_df["difficulty_label"] == "Easy"]
            .head(body.top_n)
        )
        recs = [
            RecommendedQuestion(
                question_id=str(r["question_id"]),
                question_text=str(r.get("question_text", "") or ""),
                chapter_name=str(r.get("chapter_name", "") or ""),
                difficulty_label=str(r.get("difficulty_label", "") or ""),
                score=1.0,
                in_zpd=False,
                reason="신규 학습자 — 입문 문제부터 시작합니다",
            )
            for _, r in starter.iterrows()
        ]
        return RecommendResponse(
            user_id=user_id,
            recommendations=recs,
            weak_chapters=[],
            zpd_count=0,
            message="풀이 이력이 없어 입문 문제를 추천합니다. 문제를 풀면 맞춤 추천이 시작됩니다.",
        )

    # 약점 챕터 계산 — get_user_weak_chapters 는 chapter_id(int)를 반환하므로
    # 응답 스키마(list[str])·reason 비교(chapter_name 기준)에 맞게 이름으로 변환.
    from recommender import get_user_weak_chapters
    _weak_ids = get_user_weak_chapters(user_id, user_logs_df, state.questions_df)
    _id2name = dict(zip(state.questions_df["chapter_id"], state.questions_df["chapter_name"]))
    weak_chapters = [str(_id2name.get(cid, cid)) for cid in _weak_ids]

    # DKT ZPD 확률
    dkt_probs = _build_dkt_probs(state, user_logs_df) if body.use_zpd else None

    # 추천 실행
    rec = state.recommender
    try:
        from recommender import recommend
        rec_ids = recommend(
            user_id=user_id,
            logs_df=user_logs_df,
            questions_df=state.questions_df,
            tfidf_matrix=rec["tfidf_matrix"],
            user_factors=rec["user_factors"],
            item_factors=rec["item_factors"],
            user_ids=rec["user_ids"],
            top_n=body.top_n,
            dkt_probs_map=dkt_probs,
            zpd_low=body.zpd_low,
            zpd_high=body.zpd_high,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"추천 중 오류 발생: {e}")

    q_df = state.questions_df.set_index("question_id")
    results = []
    zpd_count = 0
    for qid in rec_ids:
        if qid not in q_df.index:
            continue
        row = q_df.loc[qid]
        p_correct = dkt_probs.get(qid, -1) if dkt_probs else -1
        in_zpd = body.zpd_low <= p_correct <= body.zpd_high if dkt_probs else False
        if in_zpd:
            zpd_count += 1
        reason_parts = []
        if str(row.get("chapter_name", "")) in weak_chapters:
            reason_parts.append("약점 챕터")
        if in_zpd:
            reason_parts.append(f"ZPD 범위 (P={p_correct:.2f})")
        reason = " + ".join(reason_parts) if reason_parts else "유사 오답 패턴"

        results.append(
            RecommendedQuestion(
                question_id=qid,
                question_text=str(row.get("question_text", "") or ""),
                chapter_name=str(row.get("chapter_name", "") or ""),
                difficulty_label=str(row.get("difficulty_label", "") or "") or None,
                score=1.0,
                in_zpd=in_zpd,
                reason=reason,
                p_correct=round(p_correct, 4) if dkt_probs and p_correct >= 0 else None,
            )
        )

    return RecommendResponse(
        user_id=user_id,
        recommendations=results,
        weak_chapters=weak_chapters,
        zpd_count=zpd_count,
        message=f"DKT ZPD 추천 완료 — {zpd_count}개 최적 학습 구간 문제 포함",
    )
