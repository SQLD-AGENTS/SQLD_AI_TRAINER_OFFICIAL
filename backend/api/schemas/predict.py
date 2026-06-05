from typing import Literal, Optional

from pydantic import BaseModel


class PredictRequest(BaseModel):
    question_id: str


class PredictResponse(BaseModel):
    question_id: str
    error_probability: float
    risk_level: Literal["low", "medium", "high"]
    message: str
    source: Literal["model", "fallback"]
