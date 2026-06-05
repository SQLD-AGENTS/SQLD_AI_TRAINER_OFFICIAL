from typing import Any, Optional

from pydantic import BaseModel


class QuestionSummary(BaseModel):
    question_id: str
    chapter_name: str
    subject_name: Optional[str] = None
    question_type: Optional[str] = None
    difficulty_label: Optional[str] = None
    question_text: str
    has_sql: Optional[bool] = None


class QuestionDetail(QuestionSummary):
    choices: Optional[Any] = None
    correct_answer: Optional[Any] = None
    explanation: Optional[str] = None
    sql_content: Optional[str] = None


class QuestionListResponse(BaseModel):
    total: int
    questions: list[QuestionSummary]


class AnswerSubmitRequest(BaseModel):
    question_id: str
    selected_answer: Optional[Any] = None
    solve_time_sec: Optional[float] = None


class AnswerSubmitResponse(BaseModel):
    question_id: str
    is_correct: bool
    correct_answer: Optional[Any] = None
    message: str
