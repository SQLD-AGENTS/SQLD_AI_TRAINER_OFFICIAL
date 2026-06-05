from typing import Literal, Optional

from pydantic import BaseModel


class ExplainRequest(BaseModel):
    question_id: str
    top_k: int = 3


class SimilarQuestion(BaseModel):
    question_id: str
    question_text: str
    chapter_name: str
    similarity: float


class ExplainResponse(BaseModel):
    question_id: str
    question_text: Optional[str] = None
    original_explanation: Optional[str] = None
    rag_explanation: str
    source: Literal["rag", "fallback", "error"]
    similar_questions: list[SimilarQuestion] = []
