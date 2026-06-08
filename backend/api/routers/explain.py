from fastapi import APIRouter, HTTPException, Request

from api.schemas.explain import ExplainRequest, ExplainResponse, SimilarQuestion
from api.state import explain_cache

router = APIRouter(prefix="/explain", tags=["explain"])


@router.post("", response_model=ExplainResponse, summary="RAG AI 해설 생성 (공개)")
def generate_explanation(body: ExplainRequest, request: Request):
    """
    pgvector 유사 문제 검색 → LLM 해설 생성.
    게스트·비로그인 사용자도 이용 가능.
    동일 question_id 요청은 캐시에서 반환 (중복 API 호출 방지).
    """
    cache_key = f"{body.question_id}_{body.top_k}"
    if cache_key in explain_cache:
        return explain_cache[cache_key]

    state = request.app.state.models
    state.load_explainer_if_needed()
    if state.explainer is None:
        raise HTTPException(status_code=503, detail="RAG 해설기가 초기화되지 않았습니다.")

    df = state.questions_df
    match = df[df["question_id"] == body.question_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"문제 {body.question_id}를 찾을 수 없습니다.")
    row = match.iloc[0]

    similar_rows = state.explainer.retrieve_similar(body.question_id, k=body.top_k)
    result = state.explainer.generate_explanation(body.question_id, similar_rows)

    similar_questions = [
        SimilarQuestion(
            question_id=s["question_id"],
            question_text=s["question_text"],
            chapter_name=s["chapter_name"],
            similarity=s["similarity"],
        )
        for s in similar_rows
    ]

    response = ExplainResponse(
        question_id=body.question_id,
        question_text=str(row.get("question_text", "") or ""),
        original_explanation=str(row.get("explanation", "") or ""),
        rag_explanation=result["explanation"],
        source=result["source"],
        similar_questions=similar_questions,
    )
    explain_cache[cache_key] = response
    return response
