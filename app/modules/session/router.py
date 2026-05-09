from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.model import User
from app.modules.session import repository, service
from app.modules.session.model import UserSession
from app.modules.session.schema import (
    AnswerResult, AnswerSubmit, BatchResult, BatchSubmit,
    SessionCreate, SessionOut,
)

router = APIRouter(prefix="/sessions", tags=["session"])


def _get_session(session_id: int, db: DBSession, user: User) -> UserSession:
    s = repository.get(db, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return s


@router.post("", response_model=SessionOut)
def start_session(
    data: SessionCreate,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return service.start(db, user.id, data.exercise_id, data.lock_from_seq, data.lock_to_seq)


@router.get("/{session_id}/question")
def get_question(
    session_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    return service.current_question(db, s)


@router.get("/{session_id}/questions")
def get_all_questions(
    session_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    return service.all_questions(db, s)


@router.post("/{session_id}/answer", response_model=AnswerResult)
def submit_answer(
    session_id: int,
    data: AnswerSubmit,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    if s.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    return service.submit_answer(db, s, data.question_id, data.user_input, data.blank_answers)


@router.post("/{session_id}/answers/batch", response_model=BatchResult)
def submit_batch(
    session_id: int,
    data: BatchSubmit,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    return service.submit_batch(db, s, data.answers)


@router.post("/{session_id}/complete")
def complete_session(
    session_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    service.complete(db, s)
    return {"ok": True}


@router.post("/{session_id}/next")
def next_question(
    session_id: int,
    db: DBSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _get_session(session_id, db, user)
    if s.status == "completed":
        raise HTTPException(status_code=400, detail="Session already completed")
    return service.next_question(db, s)
