from sqlalchemy import (Boolean, Column, DateTime, Enum, Float, ForeignKey,
                        Integer, SmallInteger, Text, UniqueConstraint)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    exercise_id = Column(Integer, ForeignKey("exercises.id"), nullable=False)
    current_order = Column(SmallInteger, default=0)
    locked_start = Column(SmallInteger, nullable=True)   # NULL = no lock
    locked_end = Column(SmallInteger, nullable=True)
    status = Column(Enum("in_progress", "completed"), default="in_progress")
    started_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime)

    user = relationship("User")
    exercise = relationship("Exercise")
    answers = relationship("SessionAnswer", back_populates="session")


class SessionAnswer(Base):
    __tablename__ = "session_answers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("user_sessions.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(Integer, ForeignKey("exercise_questions.id"), nullable=False)
    user_input = Column(Text)
    is_correct = Column(Boolean)
    score = Column(Float, default=0.0)
    answered_at = Column(DateTime, server_default=func.now())

    session = relationship("UserSession", back_populates="answers")
    question = relationship("ExerciseQuestion")

    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_session_question"),
    )
