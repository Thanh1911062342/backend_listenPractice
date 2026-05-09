from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class SessionCreate(BaseModel):
    exercise_id: int
    lock_from_seq: Optional[int] = None
    lock_to_seq: Optional[int] = None


class SessionOut(BaseModel):
    id: int
    exercise_id: int
    status: str
    current_order: int
    locked_start: Optional[int]
    locked_end: Optional[int]
    started_at: datetime

    model_config = {"from_attributes": True}


class AnswerSubmit(BaseModel):
    question_id: int
    user_input: str
    blank_answers: Optional[List[str]] = None


class AnswerResult(BaseModel):
    is_correct: bool
    score: float
    correct_text: str
    user_input: str
    can_continue: bool
    is_last: bool


class BatchAnswerItem(BaseModel):
    question_id: int
    blank_answers: List[str]


class BatchSubmit(BaseModel):
    answers: List[BatchAnswerItem]


class QuestionResult(BaseModel):
    question_id: int
    is_correct: bool
    score: float
    correct_text: str
    user_input: str


class BatchResult(BaseModel):
    results: List[QuestionResult]
    all_correct: bool
