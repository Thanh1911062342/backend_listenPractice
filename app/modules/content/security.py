import hashlib
import hmac
import time

from fastapi import HTTPException

from app.config import settings

_TTL = 900  # 15 minutes


def create_audio_token(track_id: int, user_id: int) -> dict:
    exp = int(time.time()) + _TTL
    sig = _sign(track_id, user_id, exp)
    return {
        # Opaque query params — no filename, no path info
        "url": f"/api/audio?tid={track_id}&uid={user_id}&exp={exp}&sig={sig}",
        "expires_in": _TTL,
    }


def verify_audio_token(track_id: int, user_id: int, exp: int, sig: str) -> None:
    if time.time() > exp:
        raise HTTPException(status_code=403, detail="Audio token expired")
    if not hmac.compare_digest(_sign(track_id, user_id, exp), sig):
        raise HTTPException(status_code=403, detail="Invalid audio token")


def _sign(track_id: int, user_id: int, exp: int) -> str:
    msg = f"{track_id}:{user_id}:{exp}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()
