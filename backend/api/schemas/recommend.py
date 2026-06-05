from typing import Optional

from pydantic import BaseModel


class RecommendRequest(BaseModel):
    top_n: int = 10
    use_zpd: bool = True
    zpd_low: float = 0.3
    zpd_high: float = 0.6


class RecommendedQuestion(BaseModel):
    question_id: str
    question_text: str
    chapter_name: str
    difficulty_label: Optional[str] = None
    score: float
    in_zpd: bool = False
    reason: str
    p_correct: Optional[float] = None


class RecommendResponse(BaseModel):
    user_id: str
    recommendations: list[RecommendedQuestion]
    weak_chapters: list[str]
    zpd_count: int
    message: str
