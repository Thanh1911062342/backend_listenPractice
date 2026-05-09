import difflib
import json
import re
import unicodedata

from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.modules.exercise import repository as ex_repo, service as ex_service
from app.modules.exercise.model import ExerciseQuestion
from app.modules.session import repository
from app.modules.session.model import UserSession


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r'[\s　。、！？…「」【】『』〜・]', '', text)
    return text.strip()


def _fuzzy_match(user: str, correct: str, threshold: float = 0.8) -> tuple[bool, float]:
    u, c = _norm(user), _norm(correct)
    if not c:
        return True, 1.0
    if u == c:
        return True, 1.0
    ratio = difflib.SequenceMatcher(None, u, c).ratio()
    return ratio >= threshold, ratio


def _check(
    q: ExerciseQuestion,
    user_input: str,
    blank_answers: list[str] | None,
    session_id: int = 0,
) -> tuple[bool, float, str]:
    qd = q.question_data
    qt = qd["type"]

    if qt == "dictation":
        is_correct, score = _fuzzy_match(user_input, qd["correct_text"], threshold=0.75)
        correct_text = qd["correct_text"]

    elif qt == "fill_blank":
        if "correct_text" in qd and "blanks" not in qd:
            seed = session_id ^ q.display_order
            _, correct_answer = ex_service.make_blank_display(qd["correct_text"], seed)
            user_answer = blank_answers[0] if blank_answers else user_input
            is_correct, score = _fuzzy_match(user_answer, correct_answer, threshold=0.8)
            speaker = qd.get("speaker", "")
            correct_text = (
                f"[{speaker}] {qd['correct_text']}" if speaker else qd["correct_text"]
            )
        else:
            blanks = qd.get("blanks", [])
            answers = blank_answers or []
            hits, total_score = 0, 0.0
            for i, b in enumerate(blanks):
                ans = answers[i] if i < len(answers) else ""
                ok, ratio = _fuzzy_match(ans, b["correct"], threshold=0.8)
                hits += 1 if ok else 0
                total_score += ratio
            score = total_score / len(blanks) if blanks else 0.0
            is_correct = hits == len(blanks) and bool(blanks)
            correct_text = qd.get("display_text", "")
            for b in blanks:
                correct_text = correct_text.replace("＿" * len(b["correct"]), b["correct"], 1)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown question type: {qt}")

    return is_correct, score, correct_text


def _effective_range(session: UserSession, total: int) -> tuple[int, int]:
    start = session.locked_start if session.locked_start is not None else 0
    end = session.locked_end if session.locked_end is not None else total - 1
    return start, min(end, total - 1)


def start(
    db: DBSession,
    user_id: int,
    exercise_id: int,
    lock_from_seq: int | None = None,
    lock_to_seq: int | None = None,
) -> UserSession:
    total = ex_repo.count_questions(db, exercise_id)
    if total == 0:
        raise HTTPException(status_code=404, detail="Exercise has no questions")

    locked_start = locked_end = None
    if lock_from_seq is not None or lock_to_seq is not None:
        locked_start = max(0, (lock_from_seq or 1) - 1)
        locked_end = min(total - 1, (lock_to_seq or total) - 1)
        if locked_start > locked_end:
            locked_start, locked_end = locked_end, locked_start

    return repository.create(db, user_id, exercise_id, locked_start, locked_end)


def current_question(db: DBSession, session: UserSession) -> dict:
    total = ex_repo.count_questions(db, session.exercise_id)
    range_start, range_end = _effective_range(session, total)

    if session.current_order > range_end:
        raise HTTPException(status_code=400, detail="Session already completed")

    q = ex_repo.get_question_by_order(db, session.exercise_id, session.current_order)
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    order_in_range = session.current_order - range_start
    range_total = range_end - range_start + 1
    return ex_service.format_question(q, order_in_range, range_total, session_seed=session.id)


def all_questions(db: DBSession, session: UserSession) -> list[dict]:
    total = ex_repo.count_questions(db, session.exercise_id)
    range_start, range_end = _effective_range(session, total)
    questions = ex_repo.get_questions_in_range(db, session.exercise_id, range_start, range_end)
    range_total = range_end - range_start + 1
    return [
        ex_service.format_question(
            q,
            q.display_order - range_start,
            range_total,
            session_seed=session.id,
        )
        for q in questions
    ]


def submit_answer(
    db: DBSession,
    session: UserSession,
    question_id: int,
    user_input: str,
    blank_answers: list[str] | None,
) -> dict:
    q = ex_repo.get_question(db, question_id)
    if not q or q.exercise_id != session.exercise_id:
        raise HTTPException(status_code=404, detail="Question not found in this exercise")

    stored_input = (
        json.dumps(blank_answers, ensure_ascii=False)
        if blank_answers is not None
        else user_input
    )
    is_correct, score, correct_text = _check(q, user_input, blank_answers, session.id)
    repository.save_answer(db, session.id, question_id, stored_input, is_correct, score)

    total = ex_repo.count_questions(db, session.exercise_id)
    _, range_end = _effective_range(session, total)
    is_last = session.current_order >= range_end

    return {
        "is_correct": is_correct,
        "score": round(score, 2),
        "correct_text": correct_text,
        "user_input": user_input,
        "can_continue": is_correct,
        "is_last": is_last,
    }


def submit_batch(db: DBSession, session: UserSession, answers: list) -> dict:
    results = []
    for item in answers:
        q = ex_repo.get_question(db, item.question_id)
        if not q or q.exercise_id != session.exercise_id:
            continue
        blank_answers = item.blank_answers
        user_input = blank_answers[0] if blank_answers else ""
        is_correct, score, correct_text = _check(q, user_input, blank_answers, session.id)
        stored_input = json.dumps(blank_answers, ensure_ascii=False)
        repository.upsert_answer(db, session.id, item.question_id, stored_input, is_correct, score)
        results.append({
            "question_id": item.question_id,
            "is_correct": is_correct,
            "score": round(score, 2),
            "correct_text": correct_text,
            "user_input": user_input,
        })
    return {"results": results, "all_correct": all(r["is_correct"] for r in results)}


def complete(db: DBSession, session: UserSession) -> None:
    repository.complete_session(db, session)


def next_question(db: DBSession, session: UserSession) -> dict:
    total = ex_repo.count_questions(db, session.exercise_id)
    range_start, range_end = _effective_range(session, total)
    next_order = session.current_order + 1
    is_done = next_order > range_end

    repository.advance(db, session, next_order, is_done)

    if is_done:
        return {"completed": True}

    q = ex_repo.get_question_by_order(db, session.exercise_id, next_order)
    order_in_range = next_order - range_start
    range_total = range_end - range_start + 1
    return {
        "completed": False,
        "question": ex_service.format_question(
            q, order_in_range, range_total, session_seed=session.id
        ),
    }
