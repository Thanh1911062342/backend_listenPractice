import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path


_NIX_BINS = [
    "/usr/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/nix/var/nix/profiles/default/bin/ffmpeg",
    "/run/current-system/sw/bin/ffmpeg",
]


def _find_bin(name: str) -> str:
    path = shutil.which(name)
    if path:
        return path
    for candidate in _NIX_BINS:
        p = candidate.replace("ffmpeg", name)
        if os.path.isfile(p):
            return p
    raise RuntimeError(f"{name} not found — install ffmpeg on the server")

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.modules.content import repository
from app.modules.content.model import Track


def _parse_ts(ts: str) -> int:
    h, m, rest = ts.strip().split(":")
    s, ms = rest.split(",")
    return int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1_000 + int(ms)


def _ms_to_srt_ts(ms: int) -> str:
    h = ms // 3_600_000
    m = (ms % 3_600_000) // 60_000
    s = (ms % 60_000) // 1_000
    frac = ms % 1_000
    return f"{h:02d}:{m:02d}:{s:02d},{frac:03d}"


def parse_srt(content: str) -> list[dict]:
    segments = []
    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            seq = int(lines[0].strip())
            start_ms = _parse_ts(lines[1].split("-->")[0])
            end_ms = _parse_ts(lines[1].split("-->")[1])
            raw_text = " ".join(lines[2:]).strip()
            m = re.match(r"^\[([A-Z\d]+)\]\s*", raw_text)
            speaker = m.group(1) if m else None
            clean_text = re.sub(r"^\[[A-Z\d]+\]\s*", "", raw_text).strip()
            segments.append(dict(seq=seq, start_ms=start_ms, end_ms=end_ms,
                                 raw_text=raw_text, clean_text=clean_text, speaker=speaker))
        except (ValueError, IndexError):
            continue
    return segments


def segments_to_srt(segments: list[dict]) -> str:
    parts = []
    for seg in segments:
        # raw_text already contains [speaker] prefix when diarization ran
        parts.append(str(seg["seq"]))
        parts.append(f"{_ms_to_srt_ts(seg['start_ms'])} --> {_ms_to_srt_ts(seg['end_ms'])}")
        parts.append(seg["raw_text"])
        parts.append("")
    return "\n".join(parts)


def _make_base_name(category_slug: str, title: str) -> str:
    safe_title = re.sub(r"[^\w]", "_", title).strip("_")
    return f"{category_slug}_{safe_title}"


def _clear_track_exercise_data(db: Session, track_id: int) -> None:
    """Delete exercises, sessions and answers tied to a track before replacing segments."""
    from app.modules.exercise.model import Exercise, ExerciseQuestion
    from app.modules.session.model import SessionAnswer, UserSession

    exercise_ids = [
        r[0] for r in db.query(Exercise.id).filter(Exercise.track_id == track_id).all()
    ]
    if not exercise_ids:
        return

    question_ids = [
        r[0] for r in
        db.query(ExerciseQuestion.id)
        .filter(ExerciseQuestion.exercise_id.in_(exercise_ids))
        .all()
    ]
    if question_ids:
        db.query(SessionAnswer).filter(
            SessionAnswer.question_id.in_(question_ids)
        ).delete(synchronize_session=False)

    db.query(UserSession).filter(
        UserSession.exercise_id.in_(exercise_ids)
    ).delete(synchronize_session=False)

    db.query(Exercise).filter(
        Exercise.id.in_(exercise_ids)
    ).delete(synchronize_session=False)

    db.flush()


async def upload_track(
    db: Session,
    category_id: int,
    title: str,
    description: str | None,
    difficulty: str | None,
    audio_file: UploadFile,
    srt_file: UploadFile | None,
    language: str = "ja",
    n_speakers: int = 0,
) -> Track:
    cat = repository.get_category_by_id(db, category_id)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    ext = Path(audio_file.filename or "track.mp3").suffix.lower() or ".mp3"
    base_name = _make_base_name(cat.slug, title)
    audio_filename = base_name + ext
    srt_filename = base_name + ".srt"

    if repository.get_track_by_filename(db, audio_filename):
        raise HTTPException(
            status_code=409,
            detail=f"Track '{base_name}' already exists. Change the title or category.",
        )

    audio_dir = settings.STORAGE_PATH / "audio"
    srt_dir = settings.STORAGE_PATH / "srt"
    audio_dir.mkdir(parents=True, exist_ok=True)
    srt_dir.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / audio_filename
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(audio_file.file, f)

    if srt_file is not None:
        srt_content = (await srt_file.read()).decode("utf-8-sig")
        (srt_dir / srt_filename).write_text(srt_content, encoding="utf-8")
        parsed = parse_srt(srt_content)
        if not parsed:
            audio_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Could not parse SRT file")
    else:
        from app.modules.stt import service as stt_service
        try:
            parsed = stt_service.transcribe(audio_path, language, n_speakers)
        except Exception as e:
            audio_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")
        if not parsed:
            audio_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="Transcription returned no segments")
        srt_content = segments_to_srt(parsed)
        (srt_dir / srt_filename).write_text(srt_content, encoding="utf-8")

    track = repository.create_track(
        db,
        category_id=category_id,
        title=title,
        description=description,
        difficulty=difficulty,
        audio_filename=audio_filename,
        srt_filename=srt_filename,
        duration_ms=parsed[-1]["end_ms"],
    )

    repository.bulk_create_segments(db, [{"track_id": track.id, **s} for s in parsed])
    db.commit()
    db.refresh(track)
    return track


def retranscribe_track(db: Session, track: Track, language: str = "ja", n_speakers: int = 0) -> list[dict]:
    """Replace all segments (and associated exercise/session data) with a fresh Whisper transcription."""
    from app.modules.stt import service as stt_service

    audio_path = get_audio_path(track)
    segments = stt_service.transcribe(audio_path, language, n_speakers)
    if not segments:
        raise HTTPException(status_code=400, detail="Transcription returned no segments")

    _clear_track_exercise_data(db, track.id)
    repository.delete_segments_by_track(db, track.id)
    repository.bulk_create_segments(db, [{"track_id": track.id, **s} for s in segments])

    srt_path = settings.STORAGE_PATH / "srt" / track.srt_filename
    srt_path.write_text(segments_to_srt(segments), encoding="utf-8")

    repository.update_track(db, track.id, {"duration_ms": segments[-1]["end_ms"]})
    db.commit()
    return segments


async def update_track_files(
    db: Session,
    track: Track,
    audio_file: UploadFile | None,
    srt_file: UploadFile | None,
) -> Track:
    audio_dir = settings.STORAGE_PATH / "audio"
    srt_dir = settings.STORAGE_PATH / "srt"

    if audio_file is not None:
        old_ext = Path(track.audio_filename).suffix.lower()
        new_ext = Path(audio_file.filename or "track.mp3").suffix.lower() or ".mp3"
        base = Path(track.audio_filename).stem
        if new_ext != old_ext:
            (audio_dir / track.audio_filename).unlink(missing_ok=True)
            new_audio_filename = base + new_ext
        else:
            new_audio_filename = track.audio_filename
        with open(audio_dir / new_audio_filename, "wb") as f:
            shutil.copyfileobj(audio_file.file, f)
        if new_audio_filename != track.audio_filename:
            repository.update_track(db, track.id, {"audio_filename": new_audio_filename})
            db.refresh(track)

    if srt_file is not None:
        srt_content = (await srt_file.read()).decode("utf-8-sig")
        parsed = parse_srt(srt_content)
        if not parsed:
            raise HTTPException(status_code=400, detail="Could not parse SRT file")
        srt_path = srt_dir / track.srt_filename
        srt_path.write_text(srt_content, encoding="utf-8")
        _clear_track_exercise_data(db, track.id)
        repository.delete_segments_by_track(db, track.id)
        repository.bulk_create_segments(db, [{"track_id": track.id, **s} for s in parsed])
        repository.update_track(db, track.id, {"duration_ms": parsed[-1]["end_ms"]})

    repository.update_track(db, track.id, {"updated_at": datetime.now(timezone.utc)})
    db.commit()
    db.refresh(track)
    return track


def trim_audio_track(db: Session, track: Track, start_ms: int, end_ms: int, mode: str) -> Track:
    import subprocess
    import tempfile

    audio_path = get_audio_path(track)
    suffix = Path(audio_path).suffix or ".mp3"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(tmp_fd)

    try:
        start_s = f"{start_ms / 1000:.3f}"
        end_s = f"{end_ms / 1000:.3f}"

        ffmpeg = _find_bin("ffmpeg")
        ffprobe = _find_bin("ffprobe")

        if mode == "keep":
            cmd = [ffmpeg, "-y", "-i", str(audio_path), "-ss", start_s, "-to", end_s, tmp_path]
        elif mode == "cut":
            cmd = [
                ffmpeg, "-y", "-i", str(audio_path),
                "-filter_complex",
                (
                    f"[0:a]atrim=end={start_s},asetpts=PTS-STARTPTS[a1];"
                    f"[0:a]atrim=start={end_s},asetpts=PTS-STARTPTS[a2];"
                    f"[a1][a2]concat=n=2:v=0:a=1[out]"
                ),
                "-map", "[out]", tmp_path,
            ]
        else:
            raise HTTPException(status_code=400, detail="mode must be 'keep' or 'cut'")

        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"ffmpeg failed: {proc.stderr.decode(errors='replace')[:300]}"
            )

        probe = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", tmp_path],
            capture_output=True, text=True,
        )
        new_duration_ms: int | None = None
        if probe.returncode == 0 and probe.stdout.strip():
            new_duration_ms = int(float(probe.stdout.strip()) * 1000)

        shutil.move(tmp_path, str(audio_path))

        update_data: dict = {"updated_at": datetime.now(timezone.utc)}
        if new_duration_ms is not None:
            update_data["duration_ms"] = new_duration_ms
        repository.update_track(db, track.id, update_data)
        db.commit()
        db.refresh(track)
        return track

    except HTTPException:
        raise
    except Exception as exc:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=str(exc))


def delete_track_files(track: Track) -> None:
    for subdir, attr in (("audio", "audio_filename"), ("srt", "srt_filename")):
        filename = getattr(track, attr)
        if filename:
            (settings.STORAGE_PATH / subdir / filename).unlink(missing_ok=True)


def delete_track(db: Session, track: Track) -> None:
    _clear_track_exercise_data(db, track.id)
    repository.delete_segments_by_track(db, track.id)
    delete_track_files(track)
    repository.delete_track(db, track.id)


def get_audio_path(track: Track) -> Path:
    path = settings.STORAGE_PATH / "audio" / track.audio_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return path
