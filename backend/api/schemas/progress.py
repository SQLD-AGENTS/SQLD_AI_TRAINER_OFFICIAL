from typing import Optional

from pydantic import BaseModel


class ChapterStat(BaseModel):
    chapter_id: str
    chapter_name: str
    total_attempts: int
    correct_count: int
    accuracy: float
    is_weak: bool


class ProgressResponse(BaseModel):
    user_id: str
    total_attempts: int
    overall_accuracy: float
    chapter_stats: list[ChapterStat]
    weak_chapters: list[str]
    zpd_available_count: int
    message: str
