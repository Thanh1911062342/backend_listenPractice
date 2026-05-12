from sqlalchemy.orm import Session

from app.modules.content.model import Category, Segment, Track


def get_all_categories(db: Session) -> list[Category]:
    return db.query(Category).order_by(Category.display_order, Category.id).all()


def get_category_by_slug(db: Session, slug: str) -> Category | None:
    return db.query(Category).filter(Category.slug == slug).first()


def get_category_by_id(db: Session, category_id: int) -> Category | None:
    return db.query(Category).filter(Category.id == category_id).first()


def create_category(db: Session, name: str, slug: str, description: str | None,
                    type_: str, level: str | None) -> Category:
    cat = Category(name=name, slug=slug, description=description, type=type_, level=level)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return cat


def get_tracks_by_category(db: Session, category_id: int) -> list[Track]:
    return (db.query(Track)
            .filter(Track.category_id == category_id, Track.is_active == True)
            .order_by(Track.created_at.desc())
            .all())


def get_track(db: Session, track_id: int) -> Track | None:
    return db.query(Track).filter(Track.id == track_id, Track.is_active == True).first()


def create_track(db: Session, **kwargs) -> Track:
    track = Track(**kwargs)
    db.add(track)
    db.flush()
    return track


def bulk_create_segments(db: Session, rows: list[dict]) -> None:
    db.bulk_insert_mappings(Segment, rows)


def get_segments_by_track(db: Session, track_id: int) -> list[Segment]:
    return (db.query(Segment)
            .filter(Segment.track_id == track_id)
            .order_by(Segment.seq)
            .all())


def get_all_tracks(db: Session) -> list[Track]:
    return db.query(Track).filter(Track.is_active == True).order_by(Track.created_at.desc()).all()


def get_track_by_filename(db: Session, audio_filename: str) -> Track | None:
    return db.query(Track).filter(Track.audio_filename == audio_filename).first()


def update_category(db: Session, category_id: int, data: dict) -> Category | None:
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        return None
    for k, v in data.items():
        setattr(cat, k, v)
    db.commit()
    db.refresh(cat)
    return cat


def delete_category(db: Session, category_id: int) -> bool:
    cat = db.query(Category).filter(Category.id == category_id).first()
    if not cat:
        return False
    db.delete(cat)
    db.commit()
    return True


def update_track(db: Session, track_id: int, data: dict) -> Track | None:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        return None
    for k, v in data.items():
        setattr(track, k, v)
    db.commit()
    db.refresh(track)
    return track


def delete_track(db: Session, track_id: int) -> Track | None:
    track = db.query(Track).filter(Track.id == track_id).first()
    if not track:
        return None
    db.delete(track)
    db.commit()
    return track


def has_tracks(db: Session, category_id: int) -> bool:
    return db.query(Track).filter(Track.category_id == category_id).first() is not None


def delete_segments_by_track(db: Session, track_id: int) -> None:
    db.query(Segment).filter(Segment.track_id == track_id).delete(synchronize_session=False)


def get_segment(db: Session, segment_id: int) -> Segment | None:
    return db.query(Segment).filter(Segment.id == segment_id).first()


def update_segment_is_question(db: Session, segment_id: int, is_question: bool) -> Segment | None:
    seg = db.query(Segment).filter(Segment.id == segment_id).first()
    if not seg:
        return None
    seg.is_question = is_question
    db.commit()
    db.refresh(seg)
    return seg


def create_segment(
    db: Session, track_id: int, seq: int, start_ms: int, end_ms: int,
    clean_text: str, speaker: str | None, is_question: bool
) -> Segment:
    seg = Segment(
        track_id=track_id, seq=seq, start_ms=start_ms, end_ms=end_ms,
        raw_text=clean_text, clean_text=clean_text,
        speaker=speaker, is_question=is_question,
    )
    db.add(seg)
    db.commit()
    db.refresh(seg)
    return seg


def update_segment_full(
    db: Session, segment_id: int, seq: int, start_ms: int, end_ms: int,
    clean_text: str, speaker: str | None, is_question: bool
) -> Segment | None:
    seg = db.query(Segment).filter(Segment.id == segment_id).first()
    if not seg:
        return None
    seg.seq = seq
    seg.start_ms = start_ms
    seg.end_ms = end_ms
    seg.clean_text = clean_text
    seg.raw_text = clean_text
    seg.speaker = speaker
    seg.is_question = is_question
    db.commit()
    db.refresh(seg)
    return seg


def delete_segment(db: Session, segment_id: int) -> bool:
    seg = db.query(Segment).filter(Segment.id == segment_id).first()
    if not seg:
        return False
    db.delete(seg)
    db.commit()
    return True
