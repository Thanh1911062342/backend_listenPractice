import os
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.auth.model import User
from app.modules.content import repository, security, service
from app.modules.content.schema import (AdminSegmentOut, CategoryCreate,
                                         CategoryOut, CategoryUpdate,
                                         CategoryWithTracks, SegmentCreate,
                                         SegmentPatch, SegmentUpdate,
                                         TrackDetail, TrackOut, TrackUpdate,
                                         TrimRequest)

router = APIRouter(tags=["content"])


# ── Public / user-facing ─────────────────────────────────────────────────────

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return repository.get_all_categories(db)


@router.get("/categories/{slug}", response_model=CategoryWithTracks)
def get_category(slug: str, db: Session = Depends(get_db)):
    cat = repository.get_category_by_slug(db, slug)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    tracks = repository.get_tracks_by_category(db, cat.id)
    return {**cat.__dict__, "tracks": tracks}


@router.get("/tracks/{track_id}", response_model=TrackDetail)
def get_track(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    segs = [s for s in track.segments if s.is_question]
    return {**track.__dict__, "segments": segs}


# ── Audio: signed-URL flow ────────────────────────────────────────────────────

@router.get("/tracks/{track_id}/audio-token")
def get_audio_token(
    track_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    return security.create_audio_token(track_id, user.id)


@router.get("/audio")
def stream_audio_signed(
    tid: int,
    uid: int,
    exp: int,
    sig: str,
    db: Session = Depends(get_db),
):
    security.verify_audio_token(tid, uid, exp, sig)
    track = repository.get_track(db, tid)
    if not track:
        raise HTTPException(status_code=404)
    path = service.get_audio_path(track)
    return FileResponse(
        str(path),
        media_type="audio/mpeg",
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.post("/admin/categories", response_model=CategoryOut)
def create_category(
    data: CategoryCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return repository.create_category(
        db, data.name, data.slug, data.description, data.type, data.level
    )


@router.get("/admin/tracks", response_model=list[TrackOut])
def list_all_tracks(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return repository.get_all_tracks(db)


@router.post("/admin/tracks", response_model=TrackOut)
async def upload_track(
    category_id: int = Form(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    difficulty: Optional[str] = Form(None),
    audio_file: UploadFile = File(...),
    srt_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await service.upload_track(
        db, category_id, title, description, difficulty,
        audio_file, srt_file,
    )


@router.patch("/admin/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    cat = repository.update_category(db, category_id, update_data)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return cat


@router.delete("/admin/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if repository.has_tracks(db, category_id):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: category still has tracks. Remove all tracks first.",
        )
    if not repository.delete_category(db, category_id):
        raise HTTPException(status_code=404, detail="Category not found")


@router.patch("/admin/tracks/{track_id}", response_model=TrackOut)
def update_track(
    track_id: int,
    data: TrackUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    track = repository.update_track(db, track_id, update_data)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return track


@router.patch("/admin/tracks/{track_id}/files", response_model=TrackOut)
async def update_track_files(
    track_id: int,
    audio_file: Optional[UploadFile] = File(None),
    srt_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    if audio_file is None and srt_file is None:
        raise HTTPException(status_code=400, detail="No file provided")
    return await service.update_track_files(db, track, audio_file, srt_file)


@router.delete("/admin/tracks/{track_id}", status_code=204)
def delete_track(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    service.delete_track(db, track)


@router.get("/admin/tracks/{track_id}/audio")
def admin_stream_audio(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404)
    path = service.get_audio_path(track)
    return FileResponse(str(path), media_type="audio/mpeg",
                        headers={"Accept-Ranges": "bytes"})


@router.get("/admin/tracks/{track_id}/segments", response_model=list[AdminSegmentOut])
def admin_get_segments(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    return repository.get_segments_by_track(db, track_id)


@router.patch("/admin/tracks/{track_id}/segments/{segment_id}", response_model=AdminSegmentOut)
def patch_segment(
    track_id: int,
    segment_id: int,
    data: SegmentPatch,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    seg = repository.update_segment_is_question(db, segment_id, data.is_question)
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    return seg


@router.post("/admin/tracks/{track_id}/segments", response_model=AdminSegmentOut, status_code=201)
def create_segment(
    track_id: int,
    data: SegmentCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    return repository.create_segment(
        db, track_id, data.seq, data.start_ms, data.end_ms,
        data.clean_text, data.speaker, data.is_question
    )


@router.put("/admin/tracks/{track_id}/segments/{segment_id}", response_model=AdminSegmentOut)
def update_segment(
    track_id: int,
    segment_id: int,
    data: SegmentUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    seg = repository.update_segment_full(
        db, segment_id, data.seq, data.start_ms, data.end_ms,
        data.clean_text, data.speaker, data.is_question
    )
    if not seg:
        raise HTTPException(status_code=404, detail="Segment not found")
    return seg


@router.delete("/admin/tracks/{track_id}/segments/{segment_id}", status_code=204)
def delete_segment(
    track_id: int,
    segment_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    if not repository.get_track(db, track_id):
        raise HTTPException(status_code=404, detail="Track not found")
    if not repository.delete_segment(db, segment_id):
        raise HTTPException(status_code=404, detail="Segment not found")


@router.post("/admin/tracks/{track_id}/stt", response_model=list[AdminSegmentOut])
async def retranscribe_track(
    track_id: int,
    language: str = Query("ja"),
    n_speakers: int = Query(0),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    audio_path = service.get_audio_path(track)
    stt_url = os.environ.get("STT_URL", "http://localhost:8001")

    try:
        import httpx
        async with httpx.AsyncClient(timeout=600.0) as client:
            with open(audio_path, "rb") as f:
                resp = await client.post(
                    f"{stt_url}/transcribe",
                    data={"language": language, "n_speakers": str(n_speakers)},
                    files={"audio_file": (audio_path.name, f, "audio/mpeg")},
                )
        if resp.status_code != 200:
            raise HTTPException(status_code=500,
                                detail=f"STT service error: {resp.text[:300]}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503,
                            detail="STT service unavailable. Make sure stt-local is running.")

    segments = resp.json()["segments"]
    if not segments:
        raise HTTPException(status_code=422, detail="STT returned no segments.")

    service._clear_track_exercise_data(db, track_id)
    repository.delete_segments_by_track(db, track_id)
    repository.bulk_create_segments(db, [{"track_id": track_id, **s} for s in segments])
    db.commit()

    return repository.get_segments_by_track(db, track_id)


@router.post("/admin/tracks/{track_id}/merge-srt", response_model=list[AdminSegmentOut])
async def merge_srt_track(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")

    segs = repository.get_segments_by_track(db, track_id)
    if not segs:
        raise HTTPException(status_code=422, detail="No segments to merge.")

    stt_url = os.environ.get("STT_URL", "http://localhost:8001")
    payload = [
        {"seq": s.seq, "speaker": s.speaker,
         "start_ms": s.start_ms, "end_ms": s.end_ms, "text": s.clean_text}
        for s in segs
    ]

    try:
        import httpx
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{stt_url}/merge-srt", json={"segments": payload})
        if resp.status_code != 200:
            raise HTTPException(status_code=500,
                                detail=f"Merge service error: {resp.text[:300]}")
    except httpx.ConnectError:
        raise HTTPException(status_code=503,
                            detail="STT service unavailable. Make sure stt-local is running.")

    merged = resp.json()
    if not merged:
        raise HTTPException(status_code=422, detail="Merge returned no groups.")

    service._clear_track_exercise_data(db, track_id)
    repository.delete_segments_by_track(db, track_id)
    new_rows = [
        {
            "track_id":   track_id,
            "seq":        i,
            "start_ms":   g["start_ms"],
            "end_ms":     g["end_ms"],
            "speaker":    g["speaker"],
            "raw_text":   g["text"],
            "clean_text": g["text"],
            "is_question": False,
        }
        for i, g in enumerate(merged, 1)
    ]
    repository.bulk_create_segments(db, new_rows)
    db.commit()

    return repository.get_segments_by_track(db, track_id)


@router.post("/admin/tracks/{track_id}/trim", response_model=TrackOut)
def trim_track(
    track_id: int,
    data: TrimRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    return service.trim_audio_track(db, track, data.start_ms, data.end_ms, data.mode)


