from sqlalchemy.orm import Session, joinedload

from app.modules.content.model import Segment
from app.modules.exercise.model import Exercise, ExerciseQuestion


def get_by_track(db: Session, track_id: int, type_: str) -> Exercise | None:
    return (db.query(Exercise)
            .filter(Exercise.track_id == track_id, Exercise.type == type_)
            .first())


def create_exercise(db: Session, track_id: int, type_: str) -> Exercise:
    ex = Exercise(track_id=track_id, type=type_)
    db.add(ex)
    db.flush()
    return ex


def bulk_create_questions(db: Session, rows: list[dict]) -> None:
    db.bulk_insert_mappings(ExerciseQuestion, rows)


def get_question(db: Session, question_id: int) -> ExerciseQuestion | None:
    return db.query(ExerciseQuestion).filter(ExerciseQuestion.id == question_id).first()


def get_question_by_order(db: Session, exercise_id: int, order: int) -> ExerciseQuestion | None:
    return (db.query(ExerciseQuestion)
            .filter(ExerciseQuestion.exercise_id == exercise_id,
                    ExerciseQuestion.display_order == order)
            .first())


def count_questions(db: Session, exercise_id: int) -> int:
    return (db.query(ExerciseQuestion)
            .filter(ExerciseQuestion.exercise_id == exercise_id)
            .count())


def get_questions_in_range(
    db: Session, exercise_id: int, start_order: int, end_order: int
) -> list[ExerciseQuestion]:
    return (
        db.query(ExerciseQuestion)
        .options(joinedload(ExerciseQuestion.segment))
        .filter(
            ExerciseQuestion.exercise_id == exercise_id,
            ExerciseQuestion.display_order >= start_order,
            ExerciseQuestion.display_order <= end_order,
        )
        .order_by(ExerciseQuestion.display_order)
        .all()
    )
