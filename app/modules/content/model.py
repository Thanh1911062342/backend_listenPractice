from sqlalchemy import (Boolean, Column, DateTime, Enum, ForeignKey, Integer,
                        SmallInteger, String, Text)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    type = Column(Enum("jlpt", "kaiwa", "podcast", "general"), nullable=False, default="general")
    level = Column(String(10))
    display_order = Column(SmallInteger, default=0)
    created_at = Column(DateTime, server_default=func.now())

    tracks = relationship("Track", back_populates="category")


class Track(Base):
    __tablename__ = "tracks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    audio_filename = Column(String(255), nullable=False)
    srt_filename = Column(String(255))
    duration_ms = Column(Integer)
    difficulty = Column(Enum("easy", "medium", "hard"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    category = relationship("Category", back_populates="tracks")
    segments = relationship("Segment", back_populates="track", order_by="Segment.seq")
    exercises = relationship("Exercise", back_populates="track")


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    seq = Column(SmallInteger, nullable=False)
    start_ms = Column(Integer, nullable=False)
    end_ms = Column(Integer, nullable=False)
    raw_text = Column(Text, nullable=False)
    clean_text = Column(Text, nullable=False)
    speaker = Column(String(10))

    is_question = Column(Boolean, nullable=False, default=True)

    track = relationship("Track", back_populates="segments")
