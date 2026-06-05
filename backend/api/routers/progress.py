from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth import require_auth
from api.database import AnswerLog, get_db
from api.schemas.progress import ChapterStat, ProgressResponse

router = APIRouter(prefix="/progress", tags=["progress"])

WEAK_THRESHOLD = 0.5


@router.get("/{user_id}", response_model=ProgressResponse, summary="학습 진도 대시보드 (인증 필요)")
def get_progress(
    user_id: str,
    request: Request,
    user: dict = Depends(require_auth),
    db: Session = Depends(get_db),
):
    """
    챕터별 정답률, 약점 챕터, DKT ZPD 가용 문제 수를 반환합니다.
    본인 데이터만 조회 가능합니다.
    """
    if user["sub"] != user_id:
        raise HTTPException(status_code=403, detail="본인의 학습 데이터만 조회할 수 있습니다.")

    logs = db.query(AnswerLog).filter(AnswerLog.user_id == user_id).all()
    if not logs:
        return ProgressResponse(
            user_id=user_id,
            total_attempts=0,
            overall_accuracy=0.0,
            chapter_stats=[],
            weak_chapters=[],
            zpd_available_count=0,
            message="아직 풀이 이력이 없습니다. 문제를 풀어보세요!",
        )

    state = request.app.state.models
    q_df = state.questions_df.set_index("question_id")

    # 챕터별 집계
    chapter_map: dict[str, dict] = {}
    total_correct = 0

    for log in logs:
        qid = log.question_id
        chapter = "Unknown"
        if qid in q_df.index:
            chapter = str(q_df.loc[qid].get("chapter_name", "Unknown") or "Unknown")

        if chapter not in chapter_map:
            chapter_map[chapter] = {"attempts": 0, "correct": 0, "chapter_id": chapter}
        chapter_map[chapter]["attempts"] += 1
        if log.is_correct:
            chapter_map[chapter]["correct"] += 1
            total_correct += 1

    total_attempts = len(logs)
    overall_accuracy = total_correct / total_attempts if total_attempts > 0 else 0.0

    chapter_stats = []
    weak_chapters = []
    for chapter_name, info in chapter_map.items():
        acc = info["correct"] / info["attempts"] if info["attempts"] > 0 else 0.0
        is_weak = acc < WEAK_THRESHOLD
        if is_weak:
            weak_chapters.append(chapter_name)
        chapter_stats.append(
            ChapterStat(
                chapter_id=info["chapter_id"],
                chapter_name=chapter_name,
                total_attempts=info["attempts"],
                correct_count=info["correct"],
                accuracy=round(acc, 4),
                is_weak=is_weak,
            )
        )

    # ZPD 가용 문제 수 (DKT 모델 있을 때만)
    zpd_count = 0
    if state.dkt_model is not None and state.dkt_question_ids is not None and logs:
        try:
            import sys, pathlib
            _src = pathlib.Path(__file__).resolve().parent.parent.parent / "src" / "models"
            if str(_src) not in sys.path:
                sys.path.insert(0, str(_src))
            from knowledge_tracer import predict_next

            q_to_idx = {qid: i for i, qid in enumerate(state.dkt_question_ids)}
            seq = {
                "user_id": user_id,
                "question_ids": [l.question_id for l in logs],
                "is_corrects": [int(l.is_correct) for l in logs],
            }
            probs = predict_next(state.dkt_model, seq, q_to_idx, state.device)
            zpd_count = int(sum(1 for p in probs if 0.3 <= p <= 0.6))
        except Exception:
            pass

    return ProgressResponse(
        user_id=user_id,
        total_attempts=total_attempts,
        overall_accuracy=round(overall_accuracy, 4),
        chapter_stats=sorted(chapter_stats, key=lambda x: x.accuracy),
        weak_chapters=weak_chapters,
        zpd_available_count=zpd_count,
        message=f"총 {total_attempts}문제 풀이 완료, 전체 정답률 {overall_accuracy:.1%}",
    )
