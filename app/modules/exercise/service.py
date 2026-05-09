import random
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.content import repository as content_repo
from app.modules.exercise import repository
from app.modules.exercise.model import Exercise, ExerciseQuestion

# Matches kanji, hiragana, katakana runs of 2+ characters
_BLANK_RE = re.compile(r'[一-鿿㐀-䶿ぁ-ゖァ-ヺー]{2,}')


def make_blank_display(text: str, seed: int) -> tuple[str, str]:
    """
    Returns (display_text_with_＿＿＿, correct_answer).
    Deterministic for the same (text, seed); different seeds → different blank positions.
    Blanks a contiguous region covering ~30-70% of the Japanese word characters,
    always leaving at least one Japanese chunk visible outside the blank.
    """
    rng = random.Random(seed)
    matches = list(_BLANK_RE.finditer(text))

    if not matches:
        return "＿＿＿", text

    n = len(matches)
    total_chars = sum(len(m.group()) for m in matches)

    if n == 1:
        # Only one chunk — blank it (no context option)
        m = matches[0]
        return text[:m.start()] + "＿＿＿" + text[m.end():], m.group()

    # 2+ chunks: select a contiguous run covering ~30-70% of total Japanese chars
    # Never select ALL chunks — always keep ≥1 visible for context
    target = max(len(matches[0].group()), int(total_chars * rng.uniform(0.3, 0.7)))

    start_i = rng.randint(0, n - 1)
    selected = [matches[start_i]]
    covered = len(matches[start_i].group())

    i = start_i + 1
    while i < n and covered < target:
        selected.append(matches[i])
        covered += len(matches[i].group())
        i += 1

    # Safety: if all chunks ended up selected, drop the last one
    if len(selected) == n:
        selected = selected[:-1]

    blank_start = selected[0].start()
    blank_end = selected[-1].end()
    answer = text[blank_start:blank_end]
    display = text[:blank_start] + "＿＿＿" + text[blank_end:]
    return display, answer


def get_or_create(db: Session, track_id: int, ex_type: str = "fill_blank") -> Exercise:
    ex = repository.get_by_track(db, track_id, ex_type)
    if ex:
        return ex

    segments = content_repo.get_segments_by_track(db, track_id)
    if not segments:
        raise HTTPException(status_code=404, detail="Track has no segments")

    ex = repository.create_exercise(db, track_id, ex_type)

    rows = []
    for order, seg in enumerate(segments):
        if ex_type == "fill_blank":
            qd = {
                "type": "fill_blank",
                "correct_text": seg.clean_text,
                "speaker": seg.speaker or "",
                "audio_start_ms": seg.start_ms,
                "audio_end_ms": seg.end_ms,
            }
        else:
            qd = {
                "type": "dictation",
                "correct_text": seg.clean_text,
                "audio_start_ms": seg.start_ms,
                "audio_end_ms": seg.end_ms,
            }
        rows.append(dict(
            exercise_id=ex.id,
            segment_id=seg.id,
            display_order=order,
            question_data=qd,
        ))

    repository.bulk_create_questions(db, rows)
    db.commit()
    db.refresh(ex)
    return ex


def format_question(
    q: ExerciseQuestion, order: int, total: int, session_seed: int = 0
) -> dict:
    qd = q.question_data
    seg = getattr(q, "segment", None)
    is_question = seg.is_question if seg is not None else True

    out = {
        "id": q.id,
        "order": order,
        "total": total,
        "audio_start_ms": qd["audio_start_ms"],
        "audio_end_ms": qd["audio_end_ms"],
        "type": qd["type"],
        "is_question": is_question,
    }
    out["display_order"] = q.display_order

    if qd["type"] == "fill_blank":
        speaker = qd.get("speaker", "")
        out["speaker"] = speaker if speaker else None

        if not is_question:
            out["display_text"] = qd["correct_text"]
            out["blank_count"] = 0
        elif "correct_text" in qd and "blanks" not in qd:
            # New format: generate blank dynamically per session
            seed = session_seed ^ q.display_order
            display, _ = make_blank_display(qd["correct_text"], seed)
            out["display_text"] = display
            out["blank_count"] = 1
        else:
            # Legacy format (pre-computed blanks) — still supported
            out["display_text"] = qd.get("display_text", "")
            out["blank_count"] = len(qd.get("blanks", []))

    return out
