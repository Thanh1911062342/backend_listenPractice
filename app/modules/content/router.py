from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.modules.auth.dependencies import get_current_user, require_admin
from app.modules.auth.model import User
from app.modules.content import repository, security, service
from app.modules.content.schema import (AdminSegmentOut, CategoryCreate,
                                         CategoryOut, CategoryUpdate,
                                         CategoryWithTracks, SegmentPatch,
                                         TrackDetail, TrackOut, TrackUpdate)

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
    return track


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
    language: str = Form("ja"),
    n_speakers: int = Form(0),
    audio_file: UploadFile = File(...),
    srt_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    return await service.upload_track(
        db, category_id, title, description, difficulty,
        audio_file, srt_file, language, n_speakers,
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


@router.delete("/admin/tracks/{track_id}", status_code=204)
def delete_track(
    track_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    service.delete_track_files(track)
    repository.delete_track(db, track_id)


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


@router.post("/admin/tracks/{track_id}/stt", response_model=list[AdminSegmentOut])
def retranscribe_track(
    track_id: int,
    language: str = "ja",
    n_speakers: int = 0,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Re-transcribe the track's audio with Whisper and replace all segments.
    WARNING: also deletes any exercises and user sessions tied to this track.
    """
    track = repository.get_track(db, track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    service.retranscribe_track(db, track, language, n_speakers)
    return repository.get_segments_by_track(db, track_id)
