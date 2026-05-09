from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.exercise import repository, service
from app.modules.exercise.schema import ExerciseOut

router = APIRouter(tags=["exercise"])


@router.get("/tracks/{track_id}/exercise", response_model=ExerciseOut)
def get_exercise(
    track_id: int,
    type: str = "dictation",
    db: Session = Depends(get_db),
):
    ex = service.get_or_create(db, track_id, type)
    total = repository.count_questions(db, ex.id)
    return {"id": ex.id, "track_id": ex.track_id, "type": ex.type, "total_questions": total}
