from datetime import datetime

from sqlalchemy.orm import Session as DBSession

from app.modules.session.model import SessionAnswer, UserSession


def create(db: DBSession, user_id: int, exercise_id: int,
           locked_start: int | None = None, locked_end: int | None = None) -> UserSession:
    initial_order = locked_start if locked_start is not None else 0
    s = UserSession(user_id=user_id, exercise_id=exercise_id,
                    current_order=initial_order,
                    locked_start=locked_start, locked_end=locked_end)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def get(db: DBSession, session_id: int) -> UserSession | None:
    return db.query(UserSession).filter(UserSession.id == session_id).first()


def save_answer(db: DBSession, session_id: int, question_id: int,
                user_input: str, is_correct: bool, score: float) -> SessionAnswer:
    ans = SessionAnswer(session_id=session_id, question_id=question_id,
                        user_input=user_input, is_correct=is_correct, score=score)
    db.add(ans)
    db.commit()
    return ans


def upsert_answer(db: DBSession, session_id: int, question_id: int,
                  user_input: str, is_correct: bool, score: float) -> None:
    existing = (
        db.query(SessionAnswer)
        .filter_by(session_id=session_id, question_id=question_id)
        .first()
    )
    if existing:
        existing.user_input = user_input
        existing.is_correct = is_correct
        existing.score = score
        existing.answered_at = datetime.utcnow()
    else:
        db.add(SessionAnswer(
            session_id=session_id, question_id=question_id,
            user_input=user_input, is_correct=is_correct, score=score,
        ))
    db.commit()


def advance(db: DBSession, session: UserSession, next_order: int, complete: bool) -> None:
    session.current_order = next_order
    if complete:
        session.status = "completed"
        session.completed_at = datetime.utcnow()
    db.commit()


def complete_session(db: DBSession, session: UserSession) -> None:
    session.status = "completed"
    session.completed_at = datetime.utcnow()
    db.commit()
