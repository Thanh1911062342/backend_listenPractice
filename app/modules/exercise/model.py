from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, SmallInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Exercise(Base):
    __tablename__ = "exercises"

    id = Column(Integer, primary_key=True, autoincrement=True)
    track_id = Column(Integer, ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    type = Column(Enum("dictation", "fill_blank"), nullable=False, default="dictation")
    config = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

    track = relationship("Track", back_populates="exercises")
    questions = relationship(
        "ExerciseQuestion",
        back_populates="exercise",
        order_by="ExerciseQuestion.display_order",
    )


class ExerciseQuestion(Base):
    __tablename__ = "exercise_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    exercise_id = Column(Integer, ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    segment_id = Column(Integer, ForeignKey("segments.id", ondelete="CASCADE"), nullable=False)
    display_order = Column(SmallInteger, nullable=False)
    question_data = Column(JSON, nullable=False)

    exercise = relationship("Exercise", back_populates="questions")
    segment = relationship("Segment")
