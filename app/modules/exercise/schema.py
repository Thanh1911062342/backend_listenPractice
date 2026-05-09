from typing import Optional

from pydantic import BaseModel


class ExerciseOut(BaseModel):
    id: int
    track_id: int
    type: str
    total_questions: int

    model_config = {"from_attributes": True}


class QuestionOut(BaseModel):
    id: int
    order: int
    total: int
    audio_start_ms: int
    audio_end_ms: int
    type: str
    display_text: Optional[str] = None  # fill_blank only — text with ＿＿ placeholders
    blank_count: Optional[int] = None   # fill_blank only
