from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    type: str = "general"
    level: Optional[str] = None
    display_order: int = 0


class CategoryOut(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str]
    type: str
    level: Optional[str]
    display_order: int

    model_config = {"from_attributes": True}


class TrackOut(BaseModel):
    id: int
    category_id: int
    title: str
    description: Optional[str]
    duration_ms: Optional[int]
    difficulty: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SegmentOut(BaseModel):
    id: int
    seq: int
    start_ms: int
    end_ms: int
    speaker: Optional[str]
    text: Optional[str] = Field(default=None, validation_alias="clean_text")

    model_config = {"from_attributes": True, "populate_by_name": True}


class TrackDetail(TrackOut):
    segments: List[SegmentOut] = []


class CategoryWithTracks(CategoryOut):
    tracks: List[TrackOut] = []


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    level: Optional[str] = None
    display_order: Optional[int] = None


class TrackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[str] = None
    category_id: Optional[int] = None


class AdminSegmentOut(BaseModel):
    id: int
    seq: int
    start_ms: int
    end_ms: int
    speaker: Optional[str]
    raw_text: str
    clean_text: str
    is_question: bool

    model_config = {"from_attributes": True}


class SegmentPatch(BaseModel):
    is_question: bool
